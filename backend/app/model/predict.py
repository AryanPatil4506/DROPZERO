"""Inference: segments + text features -> retention curve with a band, plus per-segment drop risk.

Model v2 (trained in backend/app/model/train.py on real lecture-viewing data):
- curve: per-second drop rate (direction-constrained) -> R(k) = R(k-1) * (1 - p_drop(k)),
  then a calibration of the overall level fitted on training lectures only;
- band: empirical 10th-90th percentile of (actual - predicted) on training lectures, by position;
- risk: a dedicated drop classifier, relative to how often that position drops in training.
"""

import pickle  # loads only our own model artifact from models/, never user-supplied files
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.app.model.features import (
    FEATURES,
    MODEL_COLS,
    curve_from_hazard,
    durations_of,
    feature_matrix,
    rate_to_hazard,
)
from backend.app.schemas.features import TextFeatureSet
from backend.app.schemas.prediction import CurvePoint, Prediction, SegmentRisk
from backend.app.schemas.segment import Segment
from backend.app.settings import REPO_ROOT
from backend.app.versions import FEATURE_SCHEMA_VERSION

MODEL_PATH = REPO_ROOT / "models" / "retention_model.pkl"
LABEL = (
    "Model-estimated retention (DROPZERO internal score, not YouTube analytics). "
    "Model trained on real lecture-viewing data; the shaded band is the likely range."
)


class ModelMissing(RuntimeError):
    pass


@lru_cache
def load_model(path: Path = MODEL_PATH) -> dict:
    if not path.exists():
        raise ModelMissing("no trained model; run python scripts/train_model.py")
    with path.open("rb") as f:
        art = pickle.load(f)
    if art["features"] != FEATURES or art.get("model_cols") != MODEL_COLS or "calib" not in art:
        raise ModelMissing("model artifact does not match this code; retrain it")
    return art


# ---------------------------------------------------------------- building blocks


def segment_rates(art: dict, X: np.ndarray) -> np.ndarray:
    """Predicted per-second drop rate per segment (>= 0)."""
    return np.clip(art["model"].predict(X[:, MODEL_COLS]), 0, None)


def curve_from_rates(art: dict, rates: np.ndarray, durations: np.ndarray) -> np.ndarray:
    """Calibrated, monotone retention at each segment end."""
    raw = curve_from_hazard(rate_to_hazard(rates, durations))
    r = art["calib"].predict(raw)
    return np.minimum.accumulate(np.clip(r, 0, 1))


def calibrated_curve(art: dict, X: np.ndarray) -> np.ndarray:
    return curve_from_rates(art, segment_rates(art, X), durations_of(X))


def _pos_bin(X: np.ndarray, bins: int, col: str = "rel_end") -> np.ndarray:
    return np.minimum(bins - 1, (X[:, FEATURES.index(col)] * bins).astype(int))


def band_offsets(lectures: list[dict], art: dict, bins: int, q_lo: float, q_hi: float) -> dict:
    """Quantiles of (actual - calibrated) retention per relative-position bin (training data)."""
    res = [[] for _ in range(bins)]
    for lec in lectures:
        r = calibrated_curve(art, lec["X"])
        for b, d in zip(_pos_bin(lec["X"], bins), lec["actual_R"] - r, strict=True):
            res[b].append(d)
    return {
        "bins": bins,
        "lo": [float(np.quantile(x, q_lo)) if x else 0.0 for x in res],
        "hi": [float(np.quantile(x, q_hi)) if x else 0.0 for x in res],
    }


def band_lookup(band: dict, X: np.ndarray, key: str) -> np.ndarray:
    return np.array(band[key])[_pos_bin(X, band["bins"])]


def drop_probs(clf, X: np.ndarray) -> np.ndarray:
    """Probability that each segment is a major drop (first segment scored like the rest)."""
    return clf.predict_proba(X[:, MODEL_COLS])[:, 1]


def position_rate(drop_base: list[float], X: np.ndarray) -> np.ndarray:
    return np.array(drop_base)[_pos_bin(X, len(drop_base), "rel_start")]


def risk_levels(art: dict, X: np.ndarray) -> list[str]:
    ratio = drop_probs(art["clf"], X) / position_rate(art["drop_base"], X)
    th = art["risk_thresholds"]
    return ["high" if r >= th["high"] else "medium" if r >= th["medium"] else "low" for r in ratio]


def implied_drops(r: np.ndarray) -> np.ndarray:
    prev = np.concatenate([[1.0], r[:-1]])
    return np.clip(1 - r / np.maximum(prev, 1e-9), 0, 1)


# ---------------------------------------------------------------- API


def predict(
    segments: list[Segment], fs: TextFeatureSet, duration_s: float, art: dict | None = None
) -> Prediction:
    art = art or load_model()
    X = feature_matrix(segments, fs, duration_s)
    r = calibrated_curve(art, X)
    r_lo = np.minimum.accumulate(np.clip(r + band_lookup(art["band"], X, "lo"), 0, 1))
    r_hi = np.clip(r + band_lookup(art["band"], X, "hi"), 0, 1)
    p, p_lo, p_hi = implied_drops(r), implied_drops(r_hi), implied_drops(r_lo)
    risk = risk_levels(art, X)
    points = [CurvePoint(t=0.0, retention=1.0, lower=1.0, upper=1.0)] + [
        CurvePoint(
            t=s.end,
            retention=round(float(a), 4),
            lower=round(float(min(lo, a)), 4),
            upper=round(float(max(hi, a)), 4),
        )
        for s, a, lo, hi in zip(segments, r, r_lo, r_hi, strict=True)
    ]
    return Prediction(
        project_id=fs.project_id,
        model_version=art["version"],
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        timing_source=fs.timing_source,
        label=LABEL,
        points=points,
        segments=[
            SegmentRisk(
                segment_id=s.id,
                index=s.index,
                start=s.start,
                end=s.end,
                p_drop=round(float(p[i]), 4),
                p_drop_low=round(float(min(p_lo[i], p[i])), 4),
                p_drop_high=round(float(max(p_hi[i], p[i])), 4),
                risk=risk[i],
            )
            for i, s in enumerate(segments)
        ],
    )
