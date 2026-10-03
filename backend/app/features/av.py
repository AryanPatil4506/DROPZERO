"""Audio + visual features per segment. Deterministic given the same samples and frames."""

from typing import Any

import numpy as np

from backend.app.config import config_hash
from backend.app.features.audio.energy import frame_db, segment_audio, silence_threshold_db
from backend.app.features.audio.pitch import (
    segment_pitch,
    smooth_semitones,
    to_semitones,
    voiced_mask,
    yin_f0,
)
from backend.app.features.visual.content import (
    VisualEncoder,
    classify_frames,
    label_matrix,
    label_runs,
    segment_content,
)
from backend.app.features.visual.scenes import frame_diffs, scene_cuts, segment_visual
from backend.app.ingestion.audio import SAMPLE_RATE
from backend.app.schemas.av_features import AVFeatureSet, SegmentAVFeatures, VisualRun
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
    p_cfg = cfg["pitch"]
    f0, p_hop = yin_f0(samples, SAMPLE_RATE, p_cfg)
    voiced = voiced_mask(f0, p_hop, db, hop_s, thr)
    with np.errstate(divide="ignore", invalid="ignore"):
        semis = smooth_semitones(to_semitones(f0), p_cfg["smooth_frames"])
    pitches = [
        segment_pitch(semis, voiced, p_hop, s.start, s.end, p_cfg["min_voiced_s"]) for s in segments
    ]
    ranges = [
        p.pitch_range_st
        for p, s in zip(pitches, segments, strict=True)
        if p.pitch_range_st is not None and s.kind == "speech"
    ]
    range_median = float(np.median(ranges)) if ranges else None
    out = []
    for s, pt in zip(segments, pitches, strict=True):
        a = (
            segment_audio(db, hop_s, thr, median, s.start, s.end, a_cfg["frame_ms"] / 1000)
            if len(db)
            else None
        )
        v = segment_visual(diffs, cuts, fps, s.start, s.end, v_cfg) if has_video else None
        chunk = samples[int(s.start * SAMPLE_RATE) : int(s.end * SAMPLE_RATE)]
        clip = round(float(np.mean(np.abs(chunk) >= 0.99)), 5) if len(chunk) else None
        out.append(
            SegmentAVFeatures(
                segment_id=s.id,
                index=s.index,
                start=s.start,
                end=s.end,
                silence_ratio=a.silence_ratio if a else None,
                energy_db=a.energy_db if a else None,
                energy_variation_db=a.energy_variation_db if a else None,
                clipping_ratio=clip,
                pitch_range_st=pt.pitch_range_st,
                pitch_range_ratio=(
                    round(pt.pitch_range_st / range_median, 3)
                    if pt.pitch_range_st is not None and range_median
                    else None
                ),
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
        snr_db=round(median - float(np.percentile(db, 5)), 2) if len(voiced) else None,
        pitch_median_hz=(round(float(np.median(f0[voiced])), 1) if voiced.any() else None),
        pitch_range_median_st=round(range_median, 3) if range_median is not None else None,
        segments=out,
    )


def add_visual_content(
    fs: AVFeatureSet,
    segments: list[Segment],
    rgb: np.ndarray,
    enc: VisualEncoder,
    cfg: dict[str, Any],
) -> AVFeatureSet:
    """On-screen content type per frame and picture-speech match per segment (CLIP)."""
    if len(rgb) == 0:
        return fs
    types = cfg["types"]
    keys = [t["key"] for t in types]
    img = enc.embed_images(rgb)
    labels, _ = classify_frames(
        img, label_matrix(enc, types), keys, cfg["temperature"], cfg["min_confidence"]
    )
    fps = cfg["sample_fps"]
    speech = [s for s in segments if s.kind == "speech" and s.text.strip()]
    sp_emb = (
        dict(
            zip([s.index for s in speech], enc.embed_speech([s.text for s in speech]), strict=True)
        )
        if speech
        else {}
    )
    per = {
        s.index: segment_content(labels, img, sp_emb.get(s.index), fps, s.start, s.end)
        for s in segments
    }
    matches = [c.speech_match for c in per.values() if c.speech_match is not None]
    med = float(np.median(matches)) if matches else None
    segs = [
        a.model_copy(
            update={
                "visual_type": per[a.index].visual_type,
                "visual_type_share": per[a.index].visual_type_share,
                "speech_match": per[a.index].speech_match,
                "speech_match_ratio": (
                    round(per[a.index].speech_match / med, 3)
                    if per[a.index].speech_match is not None and med
                    else None
                ),
            }
        )
        for a in fs.segments
    ]
    runs = label_runs(labels, fps, cfg["min_run_s"])
    return fs.model_copy(
        update={
            "segments": segs,
            "visual_model": enc.model_id(),
            "visual_types": {t["key"]: t["label"] for t in types} | {"unclear": "Unclear"},
            "visual_timeline": [VisualRun(start=r.start, end=r.end, type=r.label) for r in runs],
        }
    )
