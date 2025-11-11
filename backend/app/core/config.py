"""
Application configuration using Pydantic settings
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    APP_NAME: str = "Video Chapter Maker"
    APP_ENV: str = Field(default="development", env="APP_ENV")
    DEBUG: bool = Field(default=True)
    API_V1_STR: str = "/api/v1"
    
    # Server
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    
    # OpenAI
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    GPT5_MODEL: str = "gpt-5-2025-08-07"
    GPT4O_MODEL: str = "gpt-4o"
    
    # Google Cloud
    GCP_PROJECT_ID: str = Field(default="ai-mvp-452812", env="GCP_PROJECT_ID")
    GCP_REGION: str = Field(default="us-central1", env="GCP_REGION")
    GCS_UPLOAD_BUCKET: str = Field(default="chaptermaker-uploads-ai-mvp-452812", env="GCS_UPLOAD_BUCKET")
    GCS_OUTPUT_BUCKET: str = Field(default="chaptermaker-outputs-ai-mvp-452812", env="GCS_OUTPUT_BUCKET")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(default=None, env="GOOGLE_APPLICATION_CREDENTIALS")
    
    # Cloud Tasks
    CLOUD_TASKS_QUEUE: str = Field(default="video-processing", env="CLOUD_TASKS_QUEUE")
    CLOUD_TASKS_LOCATION: str = Field(default="us-central1", env="CLOUD_TASKS_LOCATION")
    
    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-here-change-in-production",
        env="SECRET_KEY"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        env="CORS_ORIGINS"
    )
    
    # File processing limits
    MAX_VIDEO_SIZE_MB: int = 5000  # 5GB
    MAX_AUDIO_SIZE_MB: int = 500  # 500MB
    MAX_PRESENTATION_SIZE_MB: int = 100
    ALLOWED_VIDEO_EXTENSIONS: List[str] = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    ALLOWED_AUDIO_EXTENSIONS: List[str] = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"]
    ALLOWED_PRESENTATION_EXTENSIONS: List[str] = [".pptx", ".ppt", ".pdf"]
    
    # Processing settings
    TRANSCRIPTION_CHUNK_SIZE_SECONDS: int = 300  # 5 minutes chunks
    BATCH_PROCESSING_MAX_CONCURRENT: int = 5
    SIGNED_URL_EXPIRY_SECONDS: int = 3600  # 1 hour
    
    # Q&A Detection keywords
    QA_KEYWORDS: List[str] = ["q&a", "q & a", "questions", "q and a", "qa", "question and answer"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        
        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str):
            if field_name == "CORS_ORIGINS":
                return [origin.strip() for origin in raw_val.split(",")]
            return raw_val


# Create settings instance
settings = Settings()
