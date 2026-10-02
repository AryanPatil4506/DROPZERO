"""Pure numpy functions over L2-normalised embeddings: repetition, novelty, topic shifts.

All inputs are arrays plus time spans; no model calls here, so these are unit-testable with any
deterministic embedding.
"""

from dataclasses import dataclass

import numpy as np


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


@dataclass(frozen=True)
class SegRepetition:
    similarity: float | None
    match: int | None  # position in the input arrays
    count: int


def segment_repetition(
    emb: np.ndarray, starts: list[float], ends: list[float], min_gap_s: float, threshold: float
) -> list[SegRepetition]:
    """For each item, compare only with items that ended >= min_gap_s before it starts."""
    sims = emb @ emb.T
    out = []
    for i in range(len(starts)):
        cands = [j for j in range(i) if ends[j] <= starts[i] - min_gap_s]
        if not cands:
            out.append(SegRepetition(None, None, 0))
            continue
        row = sims[i, cands]
        k = int(np.argmax(row))  # first max on ties -> earliest
        out.append(SegRepetition(float(row[k]), cands[k], int(np.sum(row >= threshold))))
    return out


def sentence_matches(
    emb: np.ndarray,
    starts: list[float],
    ends: list[float],
    eligible: list[bool],
    min_gap_s: float,
    threshold: float,
) -> list[tuple[int, float] | None]:
    """Best earlier match (index, similarity) per sentence if >= threshold, else None."""
    sims = emb @ emb.T
    out: list[tuple[int, float] | None] = []
    for b in range(len(starts)):
        if not eligible[b]:
            out.append(None)
            continue
        cands = [a for a in range(b) if eligible[a] and ends[a] <= starts[b] - min_gap_s]
        if not cands:
            out.append(None)
            continue
        row = sims[b, cands]
        k = int(np.argmax(row))
        out.append((cands[k], float(row[k])) if row[k] >= threshold else None)
    return out


def novelty(emb: np.ndarray) -> list[float | None]:
    """1 - max cosine to any earlier item."""
    sims = emb @ emb.T
    return [None if i == 0 else float(1 - sims[i, :i].max()) for i in range(len(emb))]


def information_gain(
    emb: np.ndarray, starts: list[float], ends: list[float], window_s: float
) -> list[float | None]:
    """1 - cosine to the centroid of earlier items overlapping [start - window_s, start)."""
    out: list[float | None] = []
    for i in range(len(emb)):
        ctx = [j for j in range(i) if ends[j] > starts[i] - window_s]
        if not ctx:
            out.append(None)
            continue
        c = _unit(emb[ctx].mean(axis=0))
        out.append(float(1 - emb[i] @ c))
    return out


def topic_shift(emb: np.ndarray) -> list[float | None]:
    return [None if i == 0 else float(1 - emb[i] @ emb[i - 1]) for i in range(len(emb))]


def topic_boundaries(
    emb: np.ndarray,
    starts: list[float],
    block: int,
    std_k: float,
    abs_min: float,
    min_section_s: float,
) -> list[int]:
    """TextTiling-style: gap similarity between neighbouring blocks, depth scores at local
    minima, keep deep ones. Returns item indices that start a new section (never 0)."""
    n = len(emb)
    if n < 3:
        return []
    gaps = np.zeros(n)  # gaps[i]: similarity across the boundary before item i
    for i in range(1, n):
        left = _unit(emb[max(0, i - block) : i].mean(axis=0))
        right = _unit(emb[i : min(n, i + block)].mean(axis=0))
        gaps[i] = float(left @ right)
    depth = np.zeros(n)
    for i in range(1, n):
        lp = gaps[i]
        j = i - 1
        while j >= 1 and gaps[j] >= lp:
            lp = gaps[j]
            j -= 1
        rp = gaps[i]
        j = i + 1
        while j < n and gaps[j] >= rp:
            rp = gaps[j]
            j += 1
        depth[i] = (lp - gaps[i]) + (rp - gaps[i])
    minima = [
        i
        for i in range(1, n)
        if (i == 1 or gaps[i] <= gaps[i - 1]) and (i == n - 1 or gaps[i] <= gaps[i + 1])
    ]
    if not minima:
        return []
    d = depth[minima]
    cut = max(abs_min, float(d.mean() + std_k * d.std()))
    chosen: list[int] = []
    # strongest first, then enforce minimum section length
    for i in sorted(minima, key=lambda i: (-depth[i], i)):
        if depth[i] < cut:
            break
        if starts[i] - starts[0] < min_section_s:
            continue
        if all(abs(starts[i] - starts[c]) >= min_section_s for c in chosen):
            chosen.append(i)
    return sorted(chosen)
