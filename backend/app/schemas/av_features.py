from pydantic import BaseModel


class SegmentAVFeatures(BaseModel):
    segment_id: str
    index: int
    start: float
    end: float
    # audio (supporting evidence only; low energy is not "boring")
    silence_ratio: float | None
    energy_db: float | None  # vs this video's median, so it's "quieter than your average"
    energy_variation_db: float | None
    # visual (None when the upload has no video stream)
    scene_cut_count: int | None
    cuts_per_minute: float | None
    visual_change_mean: float | None  # mean frame difference, 0..1
    static_ratio: float | None  # share of sampled frames with almost no change
    longest_static_s: float | None
    seconds_since_cut: float | None  # at segment end


class AVFeatureSet(BaseModel):
    project_id: str
    av_feature_schema_version: str
    config_hash: str
    has_video: bool
    sample_fps: float | None
    scene_cuts: list[float]  # seconds
    silence_threshold_db: float | None
    segments: list[SegmentAVFeatures]
