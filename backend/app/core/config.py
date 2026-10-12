"""
Application configuration using Pydantic settings
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
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
    
    @field_validator('OPENAI_API_KEY')
    @classmethod
    def strip_api_key(cls, v: str) -> str:
        """Strip whitespace from API key to prevent header errors"""
        if v:
            return v.strip()
        return v
    GPT5_MODEL: str = "gpt-5-2025-08-07"
    GPT4O_MODEL: str = "gpt-4o"
    
    # Google Cloud
    GCP_PROJECT_ID: str = Field(default="ai-mvp-452812", env="GCP_PROJECT_ID")
    GCP_REGION: str = Field(default="us-central1", env="GCP_REGION")
    GCS_UPLOAD_BUCKET: str = Field(default="chaptermaker-uploads-ai-mvp-452812", env="GCS_UPLOAD_BUCKET")
    GCS_OUTPUT_BUCKET: str = Field(default="chaptermaker-outputs-ai-mvp-452812", env="GCS_OUTPUT_BUCKET")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(default=None, env="GOOGLE_APPLICATION_CREDENTIALS")
    
    # Cloud Tasks (used by POST /api/v1/jobs). When CLOUD_TASKS_QUEUE is empty the
    # job runs inline in this process instead (local/dev fallback).
    CLOUD_TASKS_QUEUE: str = Field(default="")
    CLOUD_TASKS_LOCATION: str = Field(default="europe-west1")
    # Public base URL of this service, used as the task target and OIDC audience.
    # If empty it is derived from the Host header of the incoming request.
    SERVICE_URL: str = Field(default="")
    # Service account Cloud Tasks mints the OIDC token for. If empty it is read
    # from the metadata server (the runtime service account).
    TASKS_SERVICE_ACCOUNT: str = Field(default="")
    # Must match the queue's maxAttempts. On the last attempt a failing job is
    # marked failed instead of being retried.
    TASK_MAX_ATTEMPTS: int = Field(default=3)
    # Cloud Tasks allows at most 30 minutes per HTTP dispatch.
    TASK_DISPATCH_DEADLINE_SECONDS: int = Field(default=1800)
    # A task stops starting new work after this many seconds and hands the rest
    # of the job to a continuation task. The longest single unit of work (one
    # GPT-5 call with retries, or audio extraction) must fit in
    # TASK_DISPATCH_DEADLINE_SECONDS - TASK_SOFT_BUDGET_SECONDS.
    TASK_SOFT_BUDGET_SECONDS: int = Field(default=600)
    # Lease held by the worker running a job; renewed every LEASE/3 seconds.
    JOB_LEASE_SECONDS: int = Field(default=120)
    # A queued/processing job with no heartbeat for this long is reported failed.
    JOB_STALE_SECONDS: int = Field(default=3600)
    # Audio is transcribed in chunks of this length; each chunk is checkpointed.
    TRANSCRIBE_CHUNK_SECONDS: int = Field(default=600)
    TRANSCRIBE_PARALLELISM: int = Field(default=4)
    TRANSCRIPTION_MODEL: str = Field(default="whisper-1")
    # Inputs larger than this are streamed into ffmpeg over HTTPS instead of
    # being downloaded to /tmp (which is memory on Cloud Run).
    STREAM_INPUT_THRESHOLD_MB: int = Field(default=512)
    FFMPEG_TIMEOUT_SECONDS: int = Field(default=1500)
    # Optional allowlist of buckets POST /api/v1/jobs may read (separated by
    # "," or ";" -- use ";" in gcloud --set-env-vars, which splits on commas).
    ALLOWED_INPUT_BUCKETS: str = Field(default="")
    
    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-here-change-in-production",
        env="SECRET_KEY"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS - Allow all origins in production (single service setup)
    CORS_ORIGINS: List[str] = Field(
        default=["*"],
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
