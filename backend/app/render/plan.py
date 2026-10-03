"""Turn an edit plan into the ordered list of source pieces the edited video is built from.

Pure and deterministic, so it is unit-tested without ffmpeg. Cuts, trims and speed-ups come from
`simulate.exposure.to_ops`, the same function the simulator uses, so the rendered video and the
simulated curve always remove the same seconds. MOVE edits are applied here too: a render can
reorder footage even though the model cannot simulate a reorder.
"""

import hashlib
import json

from pydantic import BaseModel

from backend.app.schemas.flags import Edit
from backend.app.simulate.exposure import CustomEdit, to_ops


class Piece(BaseModel):
    start: float  # source (original) seconds
    end: float
    factor: float = 1.0  # >1 = sped up

    @property
    def out_duration(self) -> float:
        return (self.end - self.start) / self.factor


class RenderPlan(BaseModel):
    pieces: list[Piece]
    applied_edit_ids: list[str]
    skipped_edit_ids: list[str]  # advice-only, overlapping, or not renderable
    applied_custom: list[CustomEdit]
    moved_edit_ids: list[str]
    source_duration_s: float
    output_duration_s: float

    def key(self) -> str:
        """Stable id for caching: the same plan is never rendered twice."""
        raw = json.dumps(
            [(round(p.start, 3), round(p.end, 3), round(p.factor, 4)) for p in self.pieces]
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _split(pieces: list[Piece], t: float) -> list[Piece]:
    out: list[Piece] = []
    for p in pieces:
        if p.start < t < p.end:
            out += [
                Piece(start=p.start, end=t, factor=p.factor),
                Piece(start=t, end=p.end, factor=p.factor),
            ]
        else:
            out.append(p)
    return out


def _apply_move(pieces: list[Piece], start: float, end: float, target: float) -> list[Piece] | None:
    """Move source range [start, end) so it plays just before source time `target`."""
    if start <= target <= end:
        return None
    for t in (start, end, target):
        pieces = _split(pieces, t)
    moving = [p for p in pieces if p.start >= start and p.end <= end]
    rest = [p for p in pieces if not (p.start >= start and p.end <= end)]
    if not moving:
        return None
    # insert before the first remaining piece that starts at/after target
    idx = next((i for i, p in enumerate(rest) if p.start >= target), len(rest))
    return rest[:idx] + moving + rest[idx:]


def build_plan(
    edits: list[Edit],
    edit_ids: list[str],
    custom: list[CustomEdit],
    duration: float,
    min_piece_s: float = 0.25,
) -> RenderPlan:
    chosen = [e for e in edits if e.id in edit_ids]
    ops, applied, skipped, applied_custom = to_ops(chosen, custom, duration)

    # timeline with cuts removed and speed-ups marked, in source order
    pieces: list[Piece] = []
    cursor = 0.0
    for o in ops:
        if o.start > cursor:
            pieces.append(Piece(start=cursor, end=o.start))
        if o.factor != float("inf"):
            pieces.append(Piece(start=o.start, end=o.end, factor=o.factor))
        cursor = max(cursor, o.end)
    if cursor < duration:
        pieces.append(Piece(start=cursor, end=duration))

    # MOVE edits (to_ops skips them; they are renderable but not simulatable)
    moved: list[str] = []
    for e in sorted(chosen, key=lambda e: e.start):
        if e.action != "MOVE" or e.target_time is None:
            continue
        nxt = _apply_move(pieces, e.start, e.end, e.target_time)
        if nxt is not None:
            pieces = nxt
            moved.append(e.id)
            if e.id in skipped:
                skipped.remove(e.id)

    pieces = [p for p in pieces if p.end - p.start >= min_piece_s]
    out = round(sum(p.out_duration for p in pieces), 3)
    return RenderPlan(
        pieces=pieces,
        applied_edit_ids=applied,
        skipped_edit_ids=skipped,
        applied_custom=applied_custom,
        moved_edit_ids=moved,
        source_duration_s=duration,
        output_duration_s=out,
    )
