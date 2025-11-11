"""
Video Chapter Maker API
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Video Chapter Maker API",
        "version": "1.0.0",
        "docs": "/api/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "project": settings.GCP_PROJECT_ID,
    }
