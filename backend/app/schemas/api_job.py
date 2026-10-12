"""
Schemas for the Inframe-facing job API (POST /api/v1/jobs and friends).
"""

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.gcs_io import InvalidGcsUri, parse_gs_uri

PRESENTATION_EXTENSIONS = (".pdf", ".pptx", ".ppt")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})*$")


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    video_uri: str = Field(..., description="gs://bucket/path to the video or audio file")
    presentation_uri: Optional[str] = Field(None, description="gs://bucket/path to a .pdf/.pptx deck")
    title: Optional[str] = Field(None, max_length=300)
    language: Optional[str] = Field(
        None, description="Spoken language (ISO-639-1, e.g. 'en'); null = auto-detect"
    )

    @field_validator("video_uri")
    @classmethod
    def _video(cls, v: str) -> str:
        try:
            return str(parse_gs_uri(v.strip()))
        except InvalidGcsUri as e:
            raise ValueError(str(e))

    @field_validator("presentation_uri")
    @classmethod
    def _deck(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        try:
            uri = parse_gs_uri(v.strip())
        except InvalidGcsUri as e:
            raise ValueError(str(e))
        if not uri.name.lower().endswith(PRESENTATION_EXTENSIONS):
            raise ValueError(f"presentation must be one of {', '.join(PRESENTATION_EXTENSIONS)}")
        return str(uri)

    @field_validator("title")
    @classmethod
    def _title(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        return v or None

    @field_validator("language")
    @classmethod
    def _language(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        if not v:
            return None
        if not _LANG_RE.match(v):
            raise ValueError("language must be a language code such as 'en' or 'da'")
        # Whisper takes ISO-639-1: keep the primary subtag ("en-GB" -> "en").
        return re.split(r"[-_]", v)[0].lower()


class CreateJobResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class ApiJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int = Field(..., ge=0, le=100)
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class ApiChapter(BaseModel):
    start_seconds: float
    title: str
    description: Optional[str] = None
    slide_uri: Optional[str] = None


class ApiTranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ApiJobResult(BaseModel):
    chapters: List[ApiChapter]
    srt_uri: str
    transcript: List[ApiTranscriptSegment]
    slides: List[str]
    qa_slide_uri: Optional[str] = None
    duration_seconds: Optional[float] = None
