"""
Ollama Model Management Service
Handles model downloads, deletion, and management
"""
import httpx
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class OllamaModelManager:
    """Manage Ollama models - list, pull, delete, and get info"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout for model downloads
        
    async def list_models(self) -> List[Dict[str, Any]]:
        """List all available models with their details"""
        try:
            response = await self.client.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get('models', []):
                    models.append({
                        'name': model.get('name'),
                        'size': model.get('size'),
                        'size_human': self._format_size(model.get('size', 0)),
                        'modified': model.get('modified_at'),
                        'digest': model.get('digest'),
                        'details': model.get('details', {})
                    })
                return models
            return []
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    async def pull_model(self, model_name: str, progress_callback=None) -> Dict[str, Any]:
        """Pull (download) a model with progress tracking"""
        try:
            # Stream the pull to get progress updates
            async with self.client.stream(
                'POST',
                f"{self.ollama_url}/api/pull",
                json={"name": model_name, "stream": True}
            ) as response:
                if response.status_code != 200:
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                
                last_status = {}
                async for line in response.aiter_lines():
                    if line:
                        try:
                            status = json.loads(line)
                            last_status = status
                            
                            if progress_callback:
                                # Calculate progress percentage
                                total = status.get('total', 0)
                                completed = status.get('completed', 0)
                                progress = (completed / total * 100) if total > 0 else 0
                                
                                await progress_callback({
                                    'status': status.get('status', 'downloading'),
                                    'progress': progress,
                                    'completed': completed,
                                    'total': total,
                                    'digest': status.get('digest', '')
                                })
                                
                        except json.JSONDecodeError:
                            continue
                
                # Check final status
                if 'error' in last_status:
                    return {"success": False, "error": last_status['error']}
                    
                return {"success": True, "model": model_name}
                
        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_model(self, model_name: str) -> Dict[str, Any]:
        """Delete a model"""
        try:
            response = await self.client.delete(
                f"{self.ollama_url}/api/delete",
                json={"name": model_name}
            )
            
            if response.status_code == 200:
                return {"success": True, "model": model_name}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Error deleting model {model_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get detailed information about a model"""
        try:
            response = await self.client.post(
                f"{self.ollama_url}/api/show",
                json={"name": model_name}
            )
            
            if response.status_code == 200:
                return response.json()
            return {}
            
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {}
    
    async def list_running_models(self) -> List[Dict[str, Any]]:
        """List currently loaded/running models"""
        try:
            response = await self.client.get(f"{self.ollama_url}/api/ps")
            if response.status_code == 200:
                data = response.json()
                return data.get('models', [])
            return []
        except Exception as e:
            logger.error(f"Error listing running models: {e}")
            return []
    
    async def search_models(self, query: str = "") -> List[Dict[str, Any]]:
        """Search for available models in Ollama library"""
        # This would need to be implemented with Ollama's model library API
        # For now, return popular models
        popular_models = [
            {
                "name": "llama3.2:1b",
                "description": "Lightweight 1B parameter model",
                "size": "1.3GB",
                "use_case": "Fast responses, basic tasks"
            },
            {
                "name": "llama3.2:3b", 
                "description": "Balanced 3B parameter model",
                "size": "2.0GB",
                "use_case": "Good balance of speed and quality"
            },
            {
                "name": "gemma3n:latest",
                "description": "Google's Gemma 3 model",
                "size": "8GB",
                "use_case": "High quality responses"
            },
            {
                "name": "mistral:7b",
                "description": "Mistral 7B model",
                "size": "4.1GB", 
                "use_case": "Strong general purpose model"
            },
            {
                "name": "phi3:mini",
                "description": "Microsoft Phi-3 Mini",
                "size": "2.3GB",
                "use_case": "Efficient small model"
            },
            {
                "name": "qwen2.5:7b",
                "description": "Alibaba Qwen 2.5",
                "size": "4.7GB",
                "use_case": "Multilingual support"
            },
            {
                "name": "deepseek-r1:7b",
                "description": "DeepSeek reasoning model",
                "size": "4.7GB",
                "use_case": "Complex reasoning tasks"
            }
        ]
        
        if query:
            return [m for m in popular_models if query.lower() in m['name'].lower() or query.lower() in m['description'].lower()]
        return popular_models
    
    async def test_model(self, model_name: str, prompt: str = "Hello, how are you?") -> Dict[str, Any]:
        """Test a model with a simple prompt"""
        try:
            response = await self.client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 50
                    }
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "response": data.get('response', ''),
                    "total_duration": data.get('total_duration', 0),
                    "tokens_per_second": self._calculate_tokens_per_second(data)
                }
            return {"success": False, "error": f"HTTP {response.status_code}"}
            
        except Exception as e:
            logger.error(f"Error testing model: {e}")
            return {"success": False, "error": str(e)}
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def _calculate_tokens_per_second(self, response_data: Dict) -> float:
        """Calculate tokens per second from response"""
        eval_count = response_data.get('eval_count', 0)
        eval_duration = response_data.get('eval_duration', 1)  # nanoseconds
        
        if eval_duration > 0:
            return eval_count / (eval_duration / 1e9)
        return 0.0
    
    async def get_model_parameters(self, model_name: str) -> Dict[str, Any]:
        """Get current parameters for a model"""
        try:
            info = await self.get_model_info(model_name)
            modelfile = info.get('modelfile', '')
            
            # Parse parameters from modelfile
            parameters = {
                'temperature': 0.7,
                'top_p': 0.9,
                'top_k': 40,
                'num_predict': 1024,
                'repeat_penalty': 1.1,
                'seed': -1,
                'num_ctx': 2048,
                'num_gpu': 999  # Use all GPU layers
            }
            
            # Extract parameters from modelfile if present
            for line in modelfile.split('\n'):
                if line.startswith('PARAMETER'):
                    parts = line.split()
                    if len(parts) >= 3:
                        param_name = parts[1]
                        param_value = parts[2]
                        try:
                            if '.' in param_value:
                                parameters[param_name] = float(param_value)
                            else:
                                parameters[param_name] = int(param_value)
                        except ValueError:
                            parameters[param_name] = param_value
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error getting model parameters: {e}")
            return {}
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

# Global instance
ollama_model_manager = OllamaModelManager()