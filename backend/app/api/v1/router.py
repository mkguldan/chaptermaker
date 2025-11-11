"""
Main API router for v1 endpoints
"""

from fastapi import APIRouter
from app.api.v1.endpoints import videos, presentations, jobs, health

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(
    videos.router,
    prefix="/videos",
    tags=["videos"]
)

api_router.include_router(
    presentations.router,
    prefix="/presentations",
    tags=["presentations"]
)

api_router.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["jobs"]
)

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)
