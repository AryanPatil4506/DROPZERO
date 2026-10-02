"""Inference: segments + text features -> survival-style retention curve with an uncertainty band.

R(0) = 1, R(k) = R(k-1) * (1 - p_drop(k)). The band comes from separate 10th/90th-percentile
hazard models (on held-out lectures it covered 95% of actual points, i.e. it is conservative).
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
    if art["features"] != FEATURES or art.get("model_cols") != MODEL_COLS:
        raise ModelMissing("model was trained on a different feature list; retrain it")
    return art


def _risk(ratio: float, art: dict) -> str:
    """Risk = predicted drop rate relative to a typical video at the same position, so intros
    (where every video loses viewers) are not all 'high'. Thresholds: train-set quantiles."""
    th = art["risk_thresholds"]
    return "high" if ratio >= th["high"] else "medium" if ratio >= th["medium"] else "low"


def predict(
    segments: list[Segment], fs: TextFeatureSet, duration_s: float, art: dict | None = None
) -> Prediction:
    art = art or load_model()
    X = feature_matrix(segments, fs, duration_s)
    # the model predicts a per-second drop rate; segment drop = 1 - exp(-rate * duration)
    d = durations_of(X)
    Xm = X[:, MODEL_COLS]
    rate = np.clip(art["model"].predict(Xm), 0, None)
    ratio = rate / np.maximum(art["baseline"].predict_rate(X), 1e-6)
    p = rate_to_hazard(rate, d)
    p_lo = np.minimum(rate_to_hazard(art["lo"].predict(Xm), d), p)
    p_hi = np.maximum(rate_to_hazard(art["hi"].predict(Xm), d), p)
    r, r_up, r_dn = curve_from_hazard(p), curve_from_hazard(p_lo), curve_from_hazard(p_hi)
    points = [CurvePoint(t=0.0, retention=1.0, lower=1.0, upper=1.0)] + [
        CurvePoint(
            t=s.end,
            retention=round(float(a), 4),
            lower=round(float(lo), 4),
            upper=round(float(hi), 4),
        )
        for s, a, lo, hi in zip(segments, r, r_dn, r_up, strict=True)
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
                p_drop_low=round(float(p_lo[i]), 4),
                p_drop_high=round(float(p_hi[i]), 4),
                risk=_risk(float(ratio[i]), art),
            )
            for i, s in enumerate(segments)
        ],
    )
