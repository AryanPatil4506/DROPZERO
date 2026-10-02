"""Simulation v2: edits remove (or shorten) the viewer's exposure to drop risk.

Each segment keeps its own predicted per-second drop rate. A CUT / TRIM removes the overlapped
seconds; a SPEED-up of factor f makes them last 1/f as long. The curve is rebuilt from the same
rates over the shortened exposure, and mapped onto the edited timeline. No re-segmentation, so a
cut never changes the prediction for untouched content (v1 re-sliced the whole timeline, which
added noise). MOVE is not simulated: the model has no notion of reordering.

The result is a model simulation and is labelled as such. The creator's media is never touched.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from backend.app.model.features import feature_matrix
from backend.app.model.predict import band_lookup, curve_from_rates, segment_rates
from backend.app.schemas.features import TextFeatureSet
from backend.app.schemas.flags import Edit
from backend.app.schemas.prediction import CurvePoint
from backend.app.schemas.segment import Segment

LABEL = (
    "Simulated: model-estimated effect of these edits (removed or sped-up time no longer exposes "
    "viewers to its predicted drop risk). Not a measured or guaranteed outcome."
)


class CustomEdit(BaseModel):
    """An edit made in the editor (not one of DROPZERO's suggestions)."""

    action: Literal["CUT", "TRIM_START", "TRIM_END", "SPEED"]
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    factor: float = Field(default=1.0, ge=1.0, le=3.0)  # SPEED only


class Op(BaseModel):
    start: float
    end: float
    factor: float  # inf = removed, >1 = sped up


class SimulationV2(BaseModel):
    label: str
    method: str = "exposure"
    applied_edit_ids: list[str]
    skipped_edit_ids: list[str]  # advice-only, MOVE, or overlapping another edit
    applied_custom: list[CustomEdit]
    original: list[CurvePoint]
    simulated: list[CurvePoint]
    original_duration_s: float
    simulated_duration_s: float
    delta: dict[str, float]  # percentage points


def to_ops(
    edits: list[Edit], custom: list[CustomEdit], duration: float
) -> tuple[list[Op], list[str], list[str], list[CustomEdit]]:
    ops: list[Op] = []
    applied, skipped, applied_custom = [], [], []

    def overlaps(a: float, b: float) -> bool:
        return any(a < o.end and b > o.start for o in ops)

    for e in sorted(edits, key=lambda e: (e.start, e.id)):
        if e.action != "CUT" or not e.simulatable or e.end <= e.start or overlaps(e.start, e.end):
            skipped.append(e.id)
            continue
        ops.append(Op(start=e.start, end=e.end, factor=float("inf")))
        applied.append(e.id)
    for c in custom:
        a, b = c.start, c.end
        if c.action == "TRIM_START":
            a, b = 0.0, c.end
        elif c.action == "TRIM_END":
            a, b = c.start, duration
        a, b = max(0.0, a), min(duration, b)
        if b <= a or overlaps(a, b):
            continue
        ops.append(Op(start=a, end=b, factor=c.factor if c.action == "SPEED" else float("inf")))
        applied_custom.append(c)
    return sorted(ops, key=lambda o: o.start), applied, skipped, applied_custom


def saved_before(ops: list[Op], t: float) -> float:
    """Seconds removed/saved from the timeline before original time t."""
    saved = 0.0
    for o in ops:
        overlap = max(0.0, min(t, o.end) - o.start)
        saved += overlap * (1 - 1 / o.factor)
    return saved


def kept_duration(ops: list[Op], a: float, b: float) -> float:
    return (b - a) - (saved_before(ops, b) - saved_before(ops, a))


def simulate_exposure(
    segments: list[Segment],
    fs: TextFeatureSet,
    duration_s: float,
    original: list[CurvePoint],
    edits: list[Edit],
    edit_ids: list[str],
    custom: list[CustomEdit],
    art: dict,
) -> SimulationV2:
    chosen = [e for e in edits if e.id in edit_ids]
    ops, applied, skipped, applied_custom = to_ops(chosen, custom, duration_s)
    X = feature_matrix(segments, fs, duration_s)
    rates = segment_rates(art, X)
    kept = np.array([kept_duration(ops, s.start, s.end) for s in segments])
    r = curve_from_rates(art, rates, np.maximum(kept, 0.0))
    lo = np.minimum.accumulate(np.clip(r + band_lookup(art["band"], X, "lo"), 0, 1))
    hi = np.clip(r + band_lookup(art["band"], X, "hi"), 0, 1)
    sim = [CurvePoint(t=0.0, retention=1.0, lower=1.0, upper=1.0)]
    for s, k, a, low, high in zip(segments, kept, r, lo, hi, strict=True):
        if k <= 1e-6:
            continue  # segment removed entirely
        sim.append(
            CurvePoint(
                t=round(s.end - saved_before(ops, s.end), 3),
                retention=round(float(a), 4),
                lower=round(float(min(low, a)), 4),
                upper=round(float(max(high, a)), 4),
            )
        )
    new_dur = round(duration_s - saved_before(ops, duration_s), 3)
    return SimulationV2(
        label=LABEL,
        applied_edit_ids=applied,
        skipped_edit_ids=skipped,
        applied_custom=applied_custom,
        original=original,
        simulated=sim,
        original_duration_s=duration_s,
        simulated_duration_s=new_dur,
        delta={
            "end_retention_pp": round(100 * (sim[-1].retention - original[-1].retention), 1),
            "avg_retention_pp": round(100 * (_avg(sim) - _avg(original)), 1),
        },
    )


def _avg(points: list[CurvePoint]) -> float:
    area = sum(
        (b.t - a.t) * (a.retention + b.retention) / 2
        for a, b in zip(points, points[1:], strict=False)
    )
    return area / points[-1].t if points[-1].t > 0 else 1.0
