from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.project import Language


class TimingSource(StrEnum):
    ASR = "asr"
    ESTIMATED = "estimated"  # script mode: shown as "estimated timing" in the UI


class Word(BaseModel):
    text: str
    start: float
    end: float
    confidence: float | None = None
    paragraph_break: bool = False  # script mode: word ends a paragraph


SentenceEnd = Literal["punct", "pause", "silence", "end"]


class Sentence(BaseModel):
    idx: int
    start: float
    end: float
    text: str
    word_start: int  # half-open slice into Transcript.words
    word_end: int
    end_reason: SentenceEnd


class Transcript(BaseModel):
    project_id: str
    language_declared: Language
    language_detected: str | None = None
    language_prob: float | None = None
    timing_source: TimingSource
    asr_model: str | None = None  # e.g. "faster-whisper/large-v3@float16"
    asr_config_hash: str | None = None
    duration_s: float
    words: list[Word]
    sentences: list[Sentence]
    mean_confidence: float | None = None
    transcript_schema_version: str
