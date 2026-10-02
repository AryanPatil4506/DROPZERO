"""Segment feature matrix for the retention-risk model.

Only language-agnostic features: the model is trained on real lecture-viewing data (MOOCCubeX,
Chinese) and applied to English/Hindi/Hinglish creator videos, so lexical features (fillers,
question words, number words) and anything the lecture data lacks (audio/visual) are excluded from
the model. They remain evidence for flags. Missing values are NaN (handled natively by the model).
"""

import numpy as np

from backend.app.schemas.features import TextFeatureSet
from backend.app.schemas.segment import Segment

FEATURES = [
    # structure / position (the per-category baseline the model learns deviations from)
    "rel_start",
    "rel_end",
    "log_start_s",
    "seg_duration_s",
    "is_first",
    "is_silence",
    # pacing relative to this video's own median
    "pace_ratio",
    # semantic (LaBSE, multilingual)
    "semantic_novelty",
    "information_gain",
    "repetition_similarity",
    "repeated_sentence_ratio",
    "repetition_count",
    "topic_shift",
    "topic_boundary",
    # short history: friction building up over the previous segments ("attention debt")
    "novelty_prev3_mean",
    "gain_prev3_mean",
    "s_since_topic_start",
]

# Segment length is NOT a model input: the model predicts a per-second rate and length only
# converts rate -> drop. (As an input it learned an artefact of how lecture starters are counted
# in the first 10 s, and made simulations depend on segment boundaries.)
MODEL_FEATURES = [f for f in FEATURES if f != "seg_duration_s"]
MODEL_COLS = [FEATURES.index(f) for f in MODEL_FEATURES]

GROUPS = {
    "position": ["rel_start", "rel_end", "log_start_s", "is_first"],
    "pacing": ["pace_ratio", "is_silence"],
    "novelty": ["semantic_novelty", "information_gain", "novelty_prev3_mean", "gain_prev3_mean"],
    "repetition": ["repetition_similarity", "repeated_sentence_ratio", "repetition_count"],
    "topics": ["topic_shift", "topic_boundary", "s_since_topic_start"],
}


def _f(x) -> float:
    return np.nan if x is None else float(x)


def feature_matrix(segments: list[Segment], fs: TextFeatureSet, duration_s: float) -> np.ndarray:
    feats = {f.index: f for f in fs.segments}
    rows = []
    nov_hist: list[float] = []
    gain_hist: list[float] = []
    topic_start = 0.0
    for s in segments:
        f = feats[s.index]
        if f.topic_boundary:
            topic_start = s.start
        row = {
            "rel_start": s.start / duration_s,
            "rel_end": s.end / duration_s,
            "log_start_s": np.log1p(s.start),
            "seg_duration_s": s.end - s.start,
            "is_first": float(s.index == 0),
            "is_silence": float(s.kind == "silence"),
            "pace_ratio": _f(f.pace_ratio),
            "semantic_novelty": _f(f.semantic_novelty),
            "information_gain": _f(f.information_gain),
            "repetition_similarity": _f(f.repetition_similarity),
            "repeated_sentence_ratio": _f(f.repeated_sentence_ratio),
            "repetition_count": float(f.repetition_count),
            "topic_shift": _f(f.topic_shift),
            "topic_boundary": float(f.topic_boundary),
            "novelty_prev3_mean": np.nanmean(nov_hist[-3:]) if nov_hist else np.nan,
            "gain_prev3_mean": np.nanmean(gain_hist[-3:]) if gain_hist else np.nan,
            "s_since_topic_start": s.start - topic_start,
        }
        rows.append([row[k] for k in FEATURES])
        if f.semantic_novelty is not None:
            nov_hist.append(f.semantic_novelty)
        if f.information_gain is not None:
            gain_hist.append(f.information_gain)
    return np.array(rows, dtype=np.float64)


def segment_hazard(segments: list[Segment], retention: np.ndarray) -> np.ndarray:
    """Observed drop probability per segment: 1 - R(end)/R(start), clipped to [0, 1].
    (R can rise slightly when viewers skip back; rises are clipped to 0 hazard.)"""
    n = len(retention)
    out = []
    for s in segments:
        r0 = retention[min(n - 1, int(s.start))]
        r1 = retention[min(n - 1, max(0, int(np.ceil(s.end)) - 1))]
        out.append(0.0 if r0 <= 0 else float(np.clip(1 - r1 / r0, 0, 1)))
    return np.array(out)


def hazard_to_rate(hazard: np.ndarray, durations: np.ndarray) -> np.ndarray:
    """Per-second drop rate (constant within a segment): -ln(1 - h) / duration. Training on rates
    makes predictions independent of how the timeline is sliced into segments."""
    h = np.clip(hazard, 0, 0.999)
    return -np.log1p(-h) / np.maximum(durations, 1e-3)


def signed_segment_rate(starts, ends, retention: np.ndarray) -> np.ndarray:
    """log(R(start) / R(end)) / duration. Unlike the clipped hazard it keeps re-watching (R can
    rise), so the product of predicted segment drops is not biased low."""
    n = len(retention)
    out = []
    for s, e in zip(starts, ends, strict=True):
        r0 = max(retention[min(n - 1, int(s))], 1e-3)
        r1 = max(retention[min(n - 1, max(0, int(np.ceil(e)) - 1))], 1e-3)
        out.append(np.log(r0 / r1) / max(e - s, 1e-3))
    return np.array(out)


def rate_to_hazard(rate: np.ndarray, durations: np.ndarray) -> np.ndarray:
    return 1 - np.exp(-np.clip(rate, 0, None) * np.maximum(durations, 0))


def durations_of(X: np.ndarray) -> np.ndarray:
    return X[:, FEATURES.index("seg_duration_s")]


def curve_from_hazard(hazard: np.ndarray) -> np.ndarray:
    """R at each segment end: R(0)=1, R(k) = R(k-1) * (1 - p_drop(k))."""
    return np.cumprod(1 - np.clip(hazard, 0, 1))
