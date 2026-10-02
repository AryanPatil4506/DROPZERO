"""Pure helpers for turning MOOCCubeX watch logs into real per-second retention curves."""

import hashlib

import numpy as np


def merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for s, e in sorted((min(a, b), max(a, b)) for a, b in intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def anchor_start(intervals: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Logs record a starter's first position a few seconds in; a viewer whose first watched
    point is <= tol started at 0, so extend that first interval to 0."""
    merged = merge_intervals(intervals)
    if merged and merged[0][0] <= tol:
        merged[0] = (0.0, merged[0][1])
    return merged


def add_coverage(diff: np.ndarray, intervals: list[tuple[float, float]]) -> None:
    """Add one viewer's watched seconds to a difference array of length duration+1. Second k is
    covered if the viewer's merged intervals overlap [k, k+1)."""
    n = len(diff) - 1
    for s, e in merge_intervals(intervals):
        a = max(0, int(np.floor(s)))
        b = min(n, int(np.ceil(e)))
        if b > a:
            diff[a] += 1
            diff[b] -= 1


def retention_from_diff(diff: np.ndarray, starters: int) -> np.ndarray:
    """Per-second share of starters watching. Can exceed the 'monotone' shape: viewers skip
    and come back; we do not force monotonicity."""
    return np.cumsum(diff[:-1]) / max(starters, 1)


def is_test(ccid: str, fraction: float) -> bool:
    """Deterministic split by lecture id."""
    h = int(hashlib.sha256(ccid.encode()).hexdigest()[:8], 16)
    return (h % 10_000) < fraction * 10_000
