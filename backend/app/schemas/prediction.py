from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.transcript import TimingSource

Risk = Literal["low", "medium", "high"]


class CurvePoint(BaseModel):
    t: float
    retention: float  # 0..1
    lower: float
    upper: float


class SegmentRisk(BaseModel):
    segment_id: str
    index: int
    start: float
    end: float
    p_drop: float
    p_drop_low: float
    p_drop_high: float
    risk: Risk


class Prediction(BaseModel):
    project_id: str
    model_version: str
    feature_schema_version: str
    timing_source: TimingSource
    label: str
    points: list[CurvePoint]
    segments: list[SegmentRisk]
