from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.transcript import TimingSource

# Why the segment ends: at a punctuated sentence end, at a pause (unpunctuated speech),
# inside an over-long sentence, before/as a long silence, or at the end of the video.
Boundary = Literal["sentence", "pause", "forced_split", "silence", "end"]


class Segment(BaseModel):
    id: str  # f"{project_id}:{index:04d}", stable across runs
    project_id: str
    index: int
    kind: Literal["speech", "silence"]
    start: float  # segments tile [0, duration] with no gaps or overlaps
    end: float
    speech_start: float | None = None
    speech_end: float | None = None
    text: str = ""
    sentence_ids: list[int] = []
    word_start: int = 0  # half-open slice into Transcript.words
    word_end: int = 0
    boundary: Boundary
    timing_source: TimingSource
    segmenter_version: str

    @property
    def duration(self) -> float:
        return self.end - self.start
