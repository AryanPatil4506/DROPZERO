from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Language(StrEnum):
    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"
    ZH = "zh"  # validation dataset only (MOOCCubeX lectures); not offered to creators


class SourceType(StrEnum):
    VIDEO = "video"
    SCRIPT = "script"


class Category(StrEnum):
    TECH = "tech"
    EDUCATION = "education"
    VLOG = "vlog"
    MUSIC = "music"
    OTHER = "other"


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

    @field_validator("language")
    @classmethod
    def _creator_languages(cls, v: Language) -> Language:
        if v == Language.ZH:
            raise ValueError("supported languages: en, hi, hinglish")
        return v


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
