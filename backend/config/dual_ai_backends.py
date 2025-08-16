"""
Dual AI Backend Configuration
Phi-4 for live/progressive summaries, Granite 3.3 for final summaries
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

# Backend configurations - Dual model setup
AI_BACKENDS = {
    "phi4_live": {
        "url": os.getenv("PHI4_URL", "http://localhost:11437"),
        "endpoint": "/completion",
        "type": "llamacpp",
        "name": "Phi-4 Mini (Live Summaries)",
        "timeout": 30,
        "health_check": "/health",
        "use_for": ["progressive", "live", "realtime"]
    },
    "granite_final": {
        "url": os.getenv("GRANITE_URL", "http://localhost:11438"),
        "endpoint": "/completion",
        "type": "llamacpp",
        "name": "Granite 3.3 8B (Final Summaries)",
        "timeout": 60,
        "health_check": "/health",
        "use_for": ["final", "comprehensive", "post_meeting"]
    }
}

def check_backend_health(backend_config: dict) -> bool:
    """Check if backend is available"""
    try:
        url = f"{backend_config['url']}{backend_config['health_check']}"
        response = requests.get(url, timeout=2)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Backend health check failed: {e}")
        return False

def get_backend_for_task(task_type: str = "progressive"):
    """
    Get appropriate backend based on task type
    
    Args:
        task_type: Type of summarization task
                  - "progressive" / "live" / "realtime" -> Phi-4
                  - "final" / "comprehensive" / "post_meeting" -> Granite 3.3
    """
    # Determine which backend to use
    if task_type in ["progressive", "live", "realtime"]:
        backend_name = "phi4_live"
        backend = AI_BACKENDS["phi4_live"]
    elif task_type in ["final", "comprehensive", "post_meeting", "analyze_meeting"]:
        backend_name = "granite_final"
        backend = AI_BACKENDS["granite_final"]
    else:
        # Default to Phi-4 for unknown tasks
        backend_name = "phi4_live"
        backend = AI_BACKENDS["phi4_live"]
    
    # Check health
    if check_backend_health(backend):
        logger.info(f"✅ Using {backend['name']} for {task_type} task")
        return backend_name, backend
    else:
        # Try fallback
        other_backend_name = "granite_final" if backend_name == "phi4_live" else "phi4_live"
        other_backend = AI_BACKENDS[other_backend_name]
        
        if check_backend_health(other_backend):
            logger.warning(f"⚠️ Primary backend unavailable, using {other_backend['name']} as fallback")
            return other_backend_name, other_backend
        
        # Return primary choice anyway even if not responding
        logger.error(f"❌ No AI backends responding, returning {backend['name']} config anyway")
        return backend_name, backend

def get_live_summary_backend():
    """Get backend specifically for live/progressive summaries"""
    return get_backend_for_task("progressive")

def get_final_summary_backend():
    """Get backend specifically for final comprehensive summaries"""
    return get_backend_for_task("final")

# Example usage in services:
"""
# In progressive_interval_manager.py or live services:
from config.dual_ai_backends import get_live_summary_backend
backend_name, backend = get_live_summary_backend()
# Uses Phi-4 on port 11437

# In unified_agent_service.py for final summaries:
from config.dual_ai_backends import get_final_summary_backend
backend_name, backend = get_final_summary_backend()
# Uses Granite 3.3 on port 11438
"""