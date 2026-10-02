"""Pure audio features from 16 kHz mono samples.

Silence is defined relative to this video's own loudness (dB below its 95th-percentile frame
energy), so a quiet microphone is not mistaken for silence. Energy is supporting evidence only.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np


def frame_db(
    samples: np.ndarray, sr: int, frame_ms: float, hop_ms: float
) -> tuple[np.ndarray, float]:
    """Per-frame RMS energy in dB, and the hop in seconds. Frame k starts at k * hop."""
    frame = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    if len(samples) < frame:
        return np.zeros(0), hop / sr
    sq = np.concatenate([[0.0], np.cumsum(samples.astype(np.float64) ** 2)])
    starts = np.arange(0, len(samples) - frame + 1, hop)
    mean_sq = (sq[starts + frame] - sq[starts]) / frame
    return 10 * np.log10(mean_sq + 1e-10), hop / sr


def silence_threshold_db(db: np.ndarray, cfg: dict[str, Any]) -> float:
    return float(np.percentile(db, 95)) - cfg["silence_db_below_p95"] if len(db) else 0.0


@dataclass(frozen=True)
class SegmentAudio:
    silence_ratio: float
    energy_db: float | None  # mean dB of non-silent frames, relative to the video's median
    energy_variation_db: float | None  # std dB of non-silent frames (flat vs lively delivery)


def segment_audio(
    db: np.ndarray,
    hop_s: float,
    threshold: float,
    video_median: float,
    start: float,
    end: float,
    frame_s: float = 0.025,
) -> SegmentAudio | None:
    # a frame belongs to the segment containing its centre
    a = max(0, int(np.ceil((start - frame_s / 2) / hop_s - 1e-9)))
    b = max(0, int(np.ceil((end - frame_s / 2) / hop_s - 1e-9)))
    seg = db[a:b]
    if len(seg) == 0:
        return None
    voiced = seg[seg >= threshold]
    return SegmentAudio(
        silence_ratio=round(float(1 - len(voiced) / len(seg)), 4),
        energy_db=round(float(voiced.mean() - video_median), 3) if len(voiced) else None,
        energy_variation_db=round(float(voiced.std()), 3) if len(voiced) > 1 else None,
    )
