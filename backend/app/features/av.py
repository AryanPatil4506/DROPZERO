"""Audio + visual features per segment. Deterministic given the same samples and frames."""

from typing import Any

import numpy as np

from backend.app.config import config_hash
from backend.app.features.audio.energy import frame_db, segment_audio, silence_threshold_db
from backend.app.features.visual.scenes import frame_diffs, scene_cuts, segment_visual
from backend.app.ingestion.audio import SAMPLE_RATE
from backend.app.schemas.av_features import AVFeatureSet, SegmentAVFeatures
from backend.app.schemas.segment import Segment
from backend.app.versions import AV_FEATURE_SCHEMA_VERSION


def detect_cuts(frames: np.ndarray | None, cfg: dict[str, Any]) -> tuple[np.ndarray, list[float]]:
    """Run before segmentation so cuts can be used as segment boundary hints."""
    if frames is None or len(frames) == 0:
        return np.zeros(0), []
    diffs = frame_diffs(frames)
    return diffs, scene_cuts(diffs, cfg["visual"]["sample_fps"], cfg["visual"])


def extract_av_features(
    project_id: str,
    segments: list[Segment],
    samples: np.ndarray,
    diffs: np.ndarray,
    cuts: list[float],
    has_video: bool,
    cfg: dict[str, Any],
) -> AVFeatureSet:
    a_cfg, v_cfg = cfg["audio"], cfg["visual"]
    db, hop_s = frame_db(samples, SAMPLE_RATE, a_cfg["frame_ms"], a_cfg["hop_ms"])
    thr = silence_threshold_db(db, a_cfg)
    voiced = db[db >= thr]
    median = float(np.median(voiced)) if len(voiced) else 0.0
    fps = v_cfg["sample_fps"]
    out = []
    for s in segments:
        a = (
            segment_audio(db, hop_s, thr, median, s.start, s.end, a_cfg["frame_ms"] / 1000)
            if len(db)
            else None
        )
        v = segment_visual(diffs, cuts, fps, s.start, s.end, v_cfg) if has_video else None
        out.append(
            SegmentAVFeatures(
                segment_id=s.id,
                index=s.index,
                start=s.start,
                end=s.end,
                silence_ratio=a.silence_ratio if a else None,
                energy_db=a.energy_db if a else None,
                energy_variation_db=a.energy_variation_db if a else None,
                scene_cut_count=v.scene_cut_count if v else None,
                cuts_per_minute=v.cuts_per_minute if v else None,
                visual_change_mean=v.visual_change_mean if v else None,
                static_ratio=v.static_ratio if v else None,
                longest_static_s=v.longest_static_s if v else None,
                seconds_since_cut=v.seconds_since_cut if v else None,
            )
        )
    return AVFeatureSet(
        project_id=project_id,
        av_feature_schema_version=AV_FEATURE_SCHEMA_VERSION,
        config_hash=config_hash(cfg),
        has_video=has_video,
        sample_fps=fps if has_video else None,
        scene_cuts=cuts,
        silence_threshold_db=round(thr, 3) if len(db) else None,
        segments=out,
    )
