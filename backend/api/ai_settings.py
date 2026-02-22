"""
AI Settings API endpoints for managing LLM and transcription configurations
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

router = APIRouter(prefix="/api", tags=["ai-settings"])

# Settings file path
SETTINGS_FILE = Path.home() / ".meeting-ops" / "ai_settings.json"

class LLMConfig(BaseModel):
    provider: str
    url: str
    apiKey: Optional[str] = None
    model: str
    enabled: bool

class TranscriptionConfig(BaseModel):
    provider: str
    model: str
    useNPU: bool
    device: str

class AISettings(BaseModel):
    ollama: Optional[LLMConfig] = None
    openai: Optional[LLMConfig] = None
    anthropic: Optional[LLMConfig] = None
    transcription: Optional[TranscriptionConfig] = None

def load_settings() -> Dict[str, Any]:
    """Load settings from file or return defaults"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    
    # Return defaults
    return {
        "ollama": {
            "provider": "ollama",
            "url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL", "gemma3n:latest"),
            "enabled": True
        },
        "openai": {
            "provider": "openai",
            "url": "https://api.openai.com/v1",
            "apiKey": os.getenv("OPENAI_API_KEY", ""),
            "model": "gpt-3.5-turbo",
            "enabled": bool(os.getenv("OPENAI_API_KEY"))
        },
        "anthropic": {
            "provider": "anthropic",
            "url": "https://api.anthropic.com",
            "apiKey": os.getenv("ANTHROPIC_API_KEY", ""),
            "model": "claude-3-opus-20240229",
            "enabled": bool(os.getenv("ANTHROPIC_API_KEY"))
        },
        "transcription": {
            "provider": "whisper",
            "model": "base",
            "useNPU": os.path.exists("/dev/accel/accel0"),
            "device": "/dev/accel/accel0"
        }
    }

def save_settings(settings: Dict[str, Any]):
    """Save settings to file and update environment"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)
    
    # Update environment variables
    if settings.get("ollama"):
        os.environ["OLLAMA_URL"] = settings["ollama"].get("url", "http://localhost:11434")
        os.environ["OLLAMA_MODEL"] = settings["ollama"].get("model", "gemma3n:latest")
    
    if settings.get("openai") and settings["openai"].get("apiKey"):
        os.environ["OPENAI_API_KEY"] = settings["openai"]["apiKey"]
    
    if settings.get("anthropic") and settings["anthropic"].get("apiKey"):
        os.environ["ANTHROPIC_API_KEY"] = settings["anthropic"]["apiKey"]

@router.get("/settings/models")
async def get_model_info():
    """Return actual running model configuration dynamically"""
    # Get LLM status from unified_llm_service
    llm_info = {"model": "unknown", "base_url": "", "llamacpp_available": False, "active_engine": "none"}
    try:
        from services.unified_llm_service import llm_service
        llm_info = llm_service.get_status()
    except Exception as e:
        llm_info["error"] = str(e)

    # Get whisper-server (Vulkan iGPU) status
    whisper_server_info = {"available": False}
    try:
        from services.whisper_server_client import whisper_server_client
        ws_available = whisper_server_client.is_available()
        whisper_server_info = {
            "available": ws_available,
            "model": "large-v3-turbo",
            "backend": "whisper.cpp Vulkan (780M iGPU)",
            "endpoint": whisper_server_client.base_url,
            "speed": "~9.6x realtime",
            "rtf": 0.104,
        }
    except Exception as e:
        whisper_server_info["error"] = str(e)

    # Get fallback STT model info from transcription_service
    stt_fallback = {}
    try:
        from services.transcription_service import transcription_service
        stt_fallback = transcription_service.get_current_model_info()
    except Exception as e:
        stt_fallback = {"error": str(e)}

    return {
        "llm": {
            "model": llm_info.get("model", "granite-3.3-2b-instruct"),
            "model_label": "Granite 3.3 2B Instruct",
            "endpoint": llm_info.get("base_url", "http://localhost:11437"),
            "available": llm_info.get("llamacpp_available", False),
            "active_engine": llm_info.get("active_engine", "none"),
            "backend": "llama.cpp Vulkan",
            "tokens_per_sec": 850,
            "context_window": 8192,
            "vram_usage": "~1.5GB"
        },
        "stt": {
            "primary": whisper_server_info,
            "fallback": stt_fallback,
            "active": "whisper-server-vulkan" if whisper_server_info.get("available") else "cpu-fallback",
        },
        "available_llm_models": [
            {
                "name": "granite-3.3-2b-instruct",
                "label": "Granite 3.3 2B Instruct",
                "tokens_per_second": 850,
                "context_window": 8192,
                "vram_usage": "~1.5GB",
                "best_for": "Summaries, chat, insights, sentiment",
                "endpoint": "http://localhost:11437",
                "status": "active" if llm_info.get("llamacpp_available") else "unavailable"
            }
        ]
    }

@router.get("/settings/ai")
async def get_ai_settings():
    """Get current AI settings"""
    return load_settings()

@router.put("/settings/ai")
async def update_ai_settings(settings: AISettings):
    """Update AI settings"""
    settings_dict = settings.dict()
    save_settings(settings_dict)
    return {"status": "success", "message": "Settings saved"}

@router.post("/test/ollama")
async def test_ollama(config: Dict[str, str]):
    """Test Ollama connection"""
    try:
        # Use urllib instead of httpx
        url = f"{config['url']}/api/tags"
        request = urllib.request.Request(url)
        
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode())
                models = data.get("models", [])
                model_names = [m["name"] for m in models]
                
                if not model_names:
                    # Try to get models from docker
                    import subprocess
                    try:
                        result = subprocess.run(
                            ["docker", "exec", "unicorn-ollama", "ollama", "list"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            lines = result.stdout.strip().split('\n')[1:]
                            model_names = [line.split()[0] for line in lines if line.strip()]
                    except:
                        pass
                
                if config["model"] in model_names:
                    return {
                        "success": True,
                        "message": f"Connected! Model '{config['model']}' is available."
                    }
                elif model_names:
                    return {
                        "success": True,
                        "message": f"Connected! Available models: {', '.join(model_names[:3])}"
                    }
                else:
                    return {
                        "success": True,
                        "message": "Connected to Ollama but no models found. Install models with: ollama pull gemma3n:latest"
                    }
        except urllib.error.URLError as e:
            return {"success": False, "message": f"Could not connect to Ollama at {config['url']}"}
            
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}

@router.post("/test/openai")
async def test_openai(config: Dict[str, str]):
    """Test OpenAI connection"""
    if not config.get("apiKey"):
        return {"success": False, "message": "API key required"}
    
    try:
        import openai
        client = openai.OpenAI(api_key=config["apiKey"])
        
        # Try a simple completion
        response = client.chat.completions.create(
            model=config.get("model", "gpt-3.5-turbo"),
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        
        return {"success": True, "message": f"Connected! Model '{config['model']}' is working."}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}

@router.post("/test/anthropic")
async def test_anthropic(config: Dict[str, str]):
    """Test Anthropic connection"""
    if not config.get("apiKey"):
        return {"success": False, "message": "API key required"}
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config["apiKey"])
        
        # Try a simple completion
        response = client.messages.create(
            model=config.get("model", "claude-3-opus-20240229"),
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        
        return {"success": True, "message": f"Connected! Model '{config['model']}' is working."}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}

@router.get("/ollama/models")
async def get_ollama_models():
    """Get list of available Ollama models"""
    try:
        settings = load_settings()
        ollama_url = settings.get("ollama", {}).get("url", "http://localhost:11434")
        
        # Try to get models from Ollama using urllib
        try:
            url = f"{ollama_url}/api/tags"
            request = urllib.request.Request(url)
            
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode())
                models = data.get("models", [])
                model_names = [m["name"] for m in models]
                if model_names:
                    return {"models": model_names}
        except:
            pass
            
        # If that doesn't work, try Docker
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "exec", "unicorn-ollama", "ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                models = []
                for line in lines:
                    if line.strip():
                        model_name = line.split()[0]
                        models.append(model_name)
                return {"models": models}
        except:
            pass
            
        return {"models": []}
    except Exception as e:
        return {"models": []}