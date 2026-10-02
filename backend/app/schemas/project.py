from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Language(StrEnum):
    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"


class SourceType(StrEnum):
    VIDEO = "video"
    SCRIPT = "script"


class Category(StrEnum):
    TECH = "tech"
    EDUCATION = "education"
    VLOG = "vlog"


class ProjectStatus(StrEnum):
    CREATED = "created"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    creator: str | None = None
    category: Category
    language: Language
    target_audience: str | None = None


class MediaInfo(BaseModel):
    duration_s: float
    has_audio: bool
    has_video: bool
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    container: str | None = None


class Project(ProjectCreate):
    id: str
    source_type: SourceType | None = None
    duration_s: float | None = None
    thumbnail_ref: str | None = None  # field reserved; thumbnail upload not built yet
    status: ProjectStatus = ProjectStatus.CREATED
    warnings: list[str] = []
    media: MediaInfo | None = None
    source_sha256: str | None = None  # sha256 of the uploaded bytes (plaintext)
    source_filename: str | None = None
    created_at: datetime
    uploaded_at: datetime | None = None
