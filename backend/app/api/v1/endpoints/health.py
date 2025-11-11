"""
Health check endpoints for monitoring
"""

from fastapi import APIRouter, Depends
from typing import Dict, Any
import logging
from datetime import datetime
from app.services.storage import StorageService
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint
    
    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@router.get("/ready")
async def readiness_check(
    storage_service: StorageService = Depends()
) -> Dict[str, Any]:
    """
    Readiness check for all services
    
    Returns:
        Service readiness status
    """
    try:
        # Check GCS connectivity
        gcs_healthy = await storage_service.check_health()
        
        # Check OpenAI API (lightweight check)
        openai_healthy = bool(settings.OPENAI_API_KEY)
        
        all_healthy = gcs_healthy and openai_healthy
        
        return {
            "status": "ready" if all_healthy else "not ready",
            "checks": {
                "gcs": "healthy" if gcs_healthy else "unhealthy",
                "openai": "configured" if openai_healthy else "not configured"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        return {
            "status": "not ready",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
