"""Step 8: apply virtual CUT/MOVE edits to the transcript timeline, then rerun segmentation,
features and the retention model. The creator's media is never touched; the result is a
model simulation and is labelled as such.

Timeline model: the original [0, duration] is split into blocks at every edit boundary. CUT drops
a block; MOVE re-inserts a block just before the block that starts at its target time. The new
timeline is the kept blocks laid end to end, and every word keeps its offset inside its block.
"""

from typing import Any

from pydantic import BaseModel

from backend.app.features.text.embedder import Embedder
from backend.app.features.text.extract import extract_text_features
from backend.app.model.predict import predict
from backend.app.schemas.flags import Edit
from backend.app.schemas.prediction import CurvePoint
from backend.app.schemas.transcript import Transcript, Word
from backend.app.segmentation.sentences import build_sentences
from backend.app.segmentation.windows import segment_transcript

LABEL = (
    "Simulated: model-estimated effect of these edits on the predicted curve. Not a measured or "
    "guaranteed outcome."
)


class Simulation(BaseModel):
    label: str
    applied_edit_ids: list[str]
    skipped_edit_ids: list[str]  # overlapping/conflicting or not simulatable (advice-only)
    original: list[CurvePoint]
    simulated: list[CurvePoint]
    original_duration_s: float
    simulated_duration_s: float
    delta: dict[str, float]  # percentage points


def resolve(edits: list[Edit]) -> tuple[list[Edit], list[str]]:
    """Keep simulatable edits in time order; drop any overlapping an already-kept one."""
    kept: list[Edit] = []
    skipped: list[str] = []
    for e in sorted(edits, key=lambda e: (e.start, e.id)):
        spans = [(e.start, e.end)] + (
            [(e.target_time, e.target_time)] if e.action == "MOVE" else []
        )
        clash = any(
            lo < k.end and hi > k.start or (k.action == "MOVE" and lo < k.target_time < hi)
            for k in kept
            for lo, hi in spans
        )
        if not e.simulatable or e.end <= e.start or clash:
            skipped.append(e.id)
        else:
            kept.append(e)
    return kept, skipped


def apply_edits(t: Transcript, edits: list[Edit], sent_cfg: dict[str, Any]) -> Transcript:
    cuts = {(e.start, e.end) for e in edits if e.action == "CUT"}
    moves = {(e.start, e.end): e.target_time for e in edits if e.action == "MOVE"}
    points = sorted(
        {0.0, t.duration_s}
        | {x for e in edits for x in (e.start, e.end)}
        | {e.target_time for e in edits if e.action == "MOVE"}
    )
    points = [p for p in points if 0.0 <= p <= t.duration_s]
    blocks = list(zip(points, points[1:], strict=False))
    moved = {b for b in blocks if any(lo <= b[0] and b[1] <= hi for lo, hi in moves)}
    order: list[tuple[float, float]] = []
    for blk in blocks:
        if blk in moved or any(lo <= blk[0] and blk[1] <= hi for lo, hi in cuts):
            continue
        for (lo, hi), target in sorted(moves.items()):
            if abs(blk[0] - target) < 1e-9:
                order += [b for b in blocks if b in moved and lo <= b[0] and b[1] <= hi]
        order.append(blk)
    new_start, pos = {}, 0.0
    for blk in order:
        new_start[blk] = pos
        pos += blk[1] - blk[0]
    words: list[Word] = []
    for blk in order:
        for w in t.words:
            mid = (w.start + w.end) / 2
            if blk[0] <= mid < blk[1] or (blk[1] == t.duration_s and mid == blk[1]):
                off = new_start[blk] - blk[0]
                words.append(
                    w.model_copy(
                        update={"start": round(w.start + off, 3), "end": round(w.end + off, 3)}
                    )
                )
    return t.model_copy(
        update={
            "words": words,
            "duration_s": round(pos, 3),
            "sentences": build_sentences(words, sent_cfg) if words else [],
        }
    )


def _avg(points: list[CurvePoint]) -> float:
    """Time-weighted mean retention over the video (trapezoid over the curve points)."""
    area = sum(
        (b.t - a.t) * (a.retention + b.retention) / 2
        for a, b in zip(points, points[1:], strict=False)
    )
    return area / points[-1].t if points[-1].t > 0 else 1.0


def simulate(
    t: Transcript,
    all_edits: list[Edit],
    edit_ids: list[str],
    original: list[CurvePoint],
    embedder: Embedder,
    cfgs: dict[str, dict[str, Any]],
) -> Simulation:
    chosen = [e for e in all_edits if e.id in edit_ids]
    kept, skipped = resolve(chosen)
    t2 = apply_edits(t, kept, cfgs["segmentation"]["sentences"])
    segs = segment_transcript(t2, cfgs["segmentation"]["windows"])
    fs = extract_text_features(t2, segs, embedder, cfgs["text_features"], cfgs["fillers"])
    sim = predict(segs, fs, t2.duration_s).points
    return Simulation(
        label=LABEL,
        applied_edit_ids=[e.id for e in kept],
        skipped_edit_ids=skipped,
        original=original,
        simulated=sim,
        original_duration_s=t.duration_s,
        simulated_duration_s=t2.duration_s,
        delta={
            "end_retention_pp": round(100 * (sim[-1].retention - original[-1].retention), 1),
            "avg_retention_pp": round(100 * (_avg(sim) - _avg(original)), 1),
        },
    )
