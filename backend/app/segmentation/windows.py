"""Sentences -> analysis windows (segments). Deterministic.

Rules (config/segmentation.yaml -> windows):
1. Sentences longer than max_s are split at their largest internal pause ("forced_split").
2. A gap between speech of >= silence_segment_min_s becomes its own "silence" segment (split into
   equal pieces <= max_s). This is what later lets us say "intro runs 18 s before the first word".
   Shorter gaps are shared: the boundary sits at the midpoint of the gap.
3. Between silences, consecutive sentences are packed into windows by dynamic programming that
   minimises squared distance from target_s, with heavy penalties outside [min_s, max_s] and a
   small preference for ending on punctuated sentences (and, from Phase 4, near scene cuts).
4. Segments tile [0, duration] exactly: every second belongs to exactly one segment, which the
   survival-style retention curve R(t) relies on.

Documented exceptions to 5 s <= length <= 15 s:
- a speech run between two long silences that is itself shorter than min_s stays one segment;
- a single sentence piece whose extent (including half of the neighbouring gaps) exceeds max_s;
- the last speech segment absorbs a trailing silence shorter than silence_segment_min_s.
"""

import math
from dataclasses import dataclass
from typing import Any

from backend.app.schemas.segment import Boundary, Segment
from backend.app.schemas.transcript import Transcript, Word
from backend.app.segmentation.sentences import join_tokens
from backend.app.versions import SEGMENTER_VERSION

_REASON_TO_BOUNDARY: dict[str, Boundary] = {
    "punct": "sentence",
    "pause": "pause",
    "silence": "pause",
    "phrase": "pause",
    "max_length": "forced_split",
    "end": "end",
}


@dataclass(frozen=True)
class _Unit:
    word_start: int
    word_end: int
    start: float
    end: float
    sentence_idx: int
    boundary: Boundary


def _split_long(words: list[Word], ws: int, we: int, max_s: float) -> list[tuple[int, int]]:
    """Recursively split words[ws:we] at the largest internal gap until each piece <= max_s."""
    if we - ws < 2 or words[we - 1].end - words[ws].start <= max_s:
        return [(ws, we)]
    mid_t = (words[ws].start + words[we - 1].end) / 2
    best_j, best_key = ws + 1, None
    for j in range(ws + 1, we):
        gap = words[j].start - words[j - 1].end
        key = (round(gap, 6), -abs(words[j].start - mid_t))
        if best_key is None or key > best_key:
            best_j, best_key = j, key
    return _split_long(words, ws, best_j, max_s) + _split_long(words, best_j, we, max_s)


def _units(t: Transcript, max_s: float) -> list[_Unit]:
    out: list[_Unit] = []
    for s in t.sentences:
        pieces = _split_long(t.words, s.word_start, s.word_end, max_s)
        for k, (ws, we) in enumerate(pieces):
            last = k == len(pieces) - 1
            out.append(
                _Unit(
                    word_start=ws,
                    word_end=we,
                    start=t.words[ws].start,
                    end=t.words[we - 1].end,
                    sentence_idx=s.idx,
                    boundary=_REASON_TO_BOUNDARY[s.end_reason] if last else "forced_split",
                )
            )
    return out


def _pack(
    units: list[_Unit], a: float, b: float, cfg: dict[str, Any], hints: list[float]
) -> list[tuple[int, int, float, float]]:
    """Partition units (one speech run spanning [a, b]) into windows. Returns (i, j, start, end)."""
    k = len(units)
    starts = [a] + [(units[i - 1].end + units[i].start) / 2 for i in range(1, k)]
    ends = starts[1:] + [b]
    target, lo, hi = cfg["target_s"], cfg["min_s"], cfg["max_s"]
    tol, bonus = cfg["hint_tolerance_s"], cfg["hint_bonus"]

    def cost(i: int, j: int) -> float:
        dur = ends[j - 1] - starts[i]
        c = (dur - target) ** 2
        c += 1e4 * max(0.0, dur - hi) ** 2 + 1e3 * max(0.0, lo - dur) ** 2
        if j < k:  # internal boundary: prefer clean sentence ends and scene cuts
            c += {"forced_split": 2.0, "pause": 0.5}.get(units[j - 1].boundary, 0.0)
            if any(abs(h - ends[j - 1]) <= tol for h in hints):
                c -= bonus
        return c

    best = [0.0] + [math.inf] * k
    back = [0] * (k + 1)
    for j in range(1, k + 1):
        for i in range(j - 1, -1, -1):
            if i < j - 1 and ends[j - 1] - starts[i] > hi:
                break
            c = best[i] + cost(i, j)
            if c < best[j]:
                best[j], back[j] = c, i
    groups = []
    j = k
    while j > 0:
        i = back[j]
        groups.append((i, j, starts[i], ends[j - 1]))
        j = i
    return groups[::-1]


def segment_transcript(
    t: Transcript, cfg: dict[str, Any], boundary_hints: list[float] | None = None
) -> list[Segment]:
    hints = sorted(boundary_hints or [])
    dur = t.duration_s
    min_sil, max_s = cfg["silence_segment_min_s"], cfg["max_s"]
    units = _units(t, max_s - cfg["forced_split_margin_s"])

    # pieces: (start, end, kind, payload)
    pieces: list[tuple[float, float, str, Any]] = []

    def add_silence(a: float, b: float) -> None:
        n = max(1, math.ceil((b - a) / max_s - 1e-9))
        step = (b - a) / n
        for m in range(n):
            pieces.append((a + m * step, b if m == n - 1 else a + (m + 1) * step, "silence", None))

    if not units:
        add_silence(0.0, dur)
    else:
        # split units into speech runs at long gaps
        runs: list[list[_Unit]] = [[units[0]]]
        for prev, u in zip(units, units[1:], strict=False):
            if u.start - prev.end >= min_sil:
                runs.append([u])
            else:
                runs[-1].append(u)
        lead = units[0].start
        if lead >= min_sil:
            add_silence(0.0, lead)
        for r, run in enumerate(runs):
            a = 0.0 if r == 0 and lead < min_sil else run[0].start
            last_run = r == len(runs) - 1
            trail = dur - run[-1].end
            b = dur if last_run and trail < min_sil else run[-1].end
            for i, j, s, e in _pack(run, a, b, cfg, hints):
                pieces.append((s, e, "speech", run[i:j]))
            if not last_run:
                add_silence(run[-1].end, runs[r + 1][0].start)
            elif trail >= min_sil:
                add_silence(run[-1].end, dur)

    segments: list[Segment] = []
    for idx, (s, e, kind, grp) in enumerate(pieces):
        is_last = idx == len(pieces) - 1
        start = 0.0 if idx == 0 else round(s, 3)
        end = round(dur, 3) if is_last else round(e, 3)
        common = dict(
            id=f"{t.project_id}:{idx:04d}",
            project_id=t.project_id,
            index=idx,
            start=start,
            end=end,
            timing_source=t.timing_source,
            segmenter_version=SEGMENTER_VERSION,
        )
        if kind == "silence":
            # word_start/end mark the insertion point in the word list (empty slice)
            pos = next((u.word_start for u in units if u.start >= e - 1e-6), len(t.words))
            segments.append(
                Segment(
                    kind="silence",
                    boundary="end" if is_last else "silence",
                    word_start=pos,
                    word_end=pos,
                    **common,
                )
            )
            continue
        ws, we = grp[0].word_start, grp[-1].word_end
        segments.append(
            Segment(
                kind="speech",
                speech_start=grp[0].start,
                speech_end=grp[-1].end,
                text=join_tokens(w.text for w in t.words[ws:we]),
                sentence_ids=sorted({u.sentence_idx for u in grp}),
                word_start=ws,
                word_end=we,
                boundary="end" if is_last else grp[-1].boundary,
                **common,
            )
        )
    return segments
