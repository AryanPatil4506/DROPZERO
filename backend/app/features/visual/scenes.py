"""Pure functions over sampled frames: scene cuts and visual monotony."""

from dataclasses import dataclass
from typing import Any

import numpy as np


def frame_diffs(frames: np.ndarray) -> np.ndarray:
    """diffs[i] = mean |frame_i - frame_{i-1}| / 255, in 0..1; diffs[0] = 0."""
    if len(frames) == 0:
        return np.zeros(0)
    f = frames.astype(np.int16)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2)) / 255.0
    return np.concatenate([[0.0], d])


def scene_cuts(diffs: np.ndarray, fps: float, cfg: dict[str, Any]) -> list[float]:
    """Cut times in seconds. A cut needs an absolute jump and a jump relative to the local median,
    so continuous camera motion is not counted as a stream of cuts."""
    half = max(1, int(round(cfg["local_window_s"] * fps / 2)))
    min_gap = cfg["min_cut_gap_s"]
    cuts: list[float] = []
    for i in range(1, len(diffs)):
        d = diffs[i]
        if d < cfg["cut_threshold"]:
            continue
        lo, hi = max(1, i - half), min(len(diffs), i + half + 1)
        local = np.delete(diffs[lo:hi], i - lo)
        med = float(np.median(local)) if len(local) else 0.0
        if d < cfg["cut_vs_local_median"] * med:
            continue
        t = round(i / fps, 3)
        if cuts and t - cuts[-1] < min_gap:
            continue
        cuts.append(t)
    return cuts


@dataclass(frozen=True)
class SegmentVisual:
    scene_cut_count: int
    cuts_per_minute: float
    visual_change_mean: float
    static_ratio: float
    longest_static_s: float
    seconds_since_cut: float  # at segment end; grows through long uncut stretches


def segment_visual(
    diffs: np.ndarray,
    cuts: list[float],
    fps: float,
    start: float,
    end: float,
    cfg: dict[str, Any],
) -> SegmentVisual | None:
    idx = [i for i in range(1, len(diffs)) if start <= i / fps < end]
    if not idx:
        return None
    d = diffs[idx]
    static = d < cfg["static_threshold"]
    longest = run = 0
    for s in static:
        run = run + 1 if s else 0
        longest = max(longest, run)
    n_cuts = sum(start <= c < end for c in cuts)
    last_cut = max((c for c in cuts if c < end), default=0.0)
    dur = max(end - start, 1e-6)
    return SegmentVisual(
        scene_cut_count=n_cuts,
        cuts_per_minute=round(n_cuts * 60 / dur, 4),
        visual_change_mean=round(float(d.mean()), 5),
        static_ratio=round(float(static.mean()), 4),
        longest_static_s=round(longest / fps, 3),
        seconds_since_cut=round(end - last_cut, 3),
    )
