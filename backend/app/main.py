"""
Video Chapter Maker API
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from app.core.config import settings
from app.api.v1.router import api_router
from app.core.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events
    """
    # Startup
    logger.info("Starting Video Chapter Maker API...")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"GCP Project: {settings.GCP_PROJECT_ID}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Video Chapter Maker API...")


# Create FastAPI app
app = FastAPI(
    title="Video Chapter Maker API",
    description="API for processing videos to generate chapters, transcriptions, and subtitles",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Configure CORS - Allow all for single service setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint (before API router)
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "project": settings.GCP_PROJECT_ID,
    }

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Mount static files for frontend (if they exist)
static_dir = Path(__file__).parent.parent / "static"
logger.info(f"Checking for static directory at: {static_dir}")
if static_dir.exists() and (static_dir / "index.html").exists():
    logger.info("Static directory found, serving frontend")
    
    # Mount assets directory
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # Catch-all route for SPA (must be last!)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes"""
        # Skip API routes
        if full_path.startswith("api/"):
            return {"error": "Not found"}, 404
            
        # Check if file exists in static directory
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        # Default to index.html for SPA routing
        return FileResponse(static_dir / "index.html")
else:
    logger.warning(f"Static directory not found at {static_dir}, serving API only")
    
    # Fallback root endpoint when no frontend
    @app.get("/")
    async def root():
        """Root endpoint - API only mode"""
        return {
            "message": "Video Chapter Maker API",
            "version": "1.0.0",
            "docs": "/api/docs",
            "note": "Frontend not available in this deployment"
        }
