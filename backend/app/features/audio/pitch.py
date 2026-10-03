"""Pure pitch features from 16 kHz mono samples: how much the voice moves (flat vs lively delivery).

F0 is tracked with YIN (de Cheveigné & Kawahara, 2002) in numpy: difference function, cumulative
mean normalised difference (CMND), first dip below `threshold`, parabolic refinement. A frame is
voiced only if YIN finds a clear period AND the frame is not silent by this video's own loudness.

Pitch range is measured in semitones (p90 - p10 of voiced frames), so it is independent of how
high or low the speaker's voice is, and judged against THIS video's own typical range. Supporting
evidence only: a calm, even delivery is not boring by itself.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np


def yin_f0(samples: np.ndarray, sr: int, cfg: dict[str, Any]) -> tuple[np.ndarray, float]:
    """Per-frame F0 in Hz (NaN = unvoiced) and the hop in seconds. Frame k starts at k * hop."""
    frame = int(sr * cfg["frame_ms"] / 1000)
    hop = int(sr * cfg["hop_ms"] / 1000)
    min_lag = int(sr / cfg["fmax_hz"])
    max_lag = int(sr / cfg["fmin_hz"])
    w = frame - max_lag  # integration window
    if w < max_lag or len(samples) < frame:
        return np.full(0, np.nan), hop / sr
    x = samples.astype(np.float64)
    starts = np.arange(0, len(x) - frame + 1, hop)
    n_fft = 1 << int(np.ceil(np.log2(frame + w)))
    sq = np.concatenate([[0.0], np.cumsum(x**2)])
    lags = np.arange(max_lag + 1)
    f0 = np.full(len(starts), np.nan)
    for b in range(0, len(starts), cfg["batch_frames"]):
        st = starts[b : b + cfg["batch_frames"]]
        idx = st[:, None] + np.arange(frame)[None, :]
        fr = x[idx]
        # cross[j, tau] = sum_{i < w} fr[j, i] * fr[j, i + tau]
        a = np.fft.rfft(fr[:, :w], n_fft)
        c = np.fft.rfft(fr, n_fft)
        cross = np.fft.irfft(np.conj(a) * c, n_fft)[:, : max_lag + 1]
        e0 = (sq[st + w] - sq[st])[:, None]
        et = sq[st[:, None] + lags[None, :] + w] - sq[st[:, None] + lags[None, :]]
        d = np.maximum(e0 + et - 2 * cross, 0.0)
        d[:, 0] = 0.0
        cum = np.cumsum(d[:, 1:], axis=1)
        cmnd = np.ones_like(d)
        cmnd[:, 1:] = d[:, 1:] * lags[None, 1:] / np.maximum(cum, 1e-12)
        below = cmnd[:, min_lag:max_lag] < cfg["threshold"]
        has = below.any(axis=1) & (e0[:, 0] > 1e-8 * w)  # digital silence has no period
        for j in np.nonzero(has)[0]:
            tau = min_lag + int(np.argmax(below[j]))
            while tau + 1 < max_lag and cmnd[j, tau + 1] < cmnd[j, tau]:
                tau += 1  # walk down to the bottom of the dip
            y0, y1, y2 = cmnd[j, tau - 1], cmnd[j, tau], cmnd[j, tau + 1]
            den = y0 - 2 * y1 + y2
            shift = 0.5 * (y0 - y2) / den if abs(den) > 1e-12 else 0.0
            f0[b + j] = sr / (tau + float(np.clip(shift, -1, 1)))
    return f0, hop / sr


def to_semitones(f0: np.ndarray) -> np.ndarray:
    return 12 * np.log2(f0 / 100.0)


def smooth_semitones(st: np.ndarray, k: int) -> np.ndarray:
    """Median filter over voiced frames only (removes single-frame octave jumps)."""
    out = st.copy()
    if k <= 1:
        return out
    h = k // 2
    for i in np.nonzero(~np.isnan(st))[0]:
        win = st[max(0, i - h) : i + h + 1]
        out[i] = np.nanmedian(win)
    return out


def voiced_mask(f0: np.ndarray, f0_hop_s: float, db: np.ndarray, db_hop_s: float, thr: float):
    """Voiced = YIN found a period and the loudness frame at the same time is not silence."""
    if len(db) == 0:
        return ~np.isnan(f0)
    k = np.minimum((np.arange(len(f0)) * f0_hop_s / db_hop_s).astype(int), len(db) - 1)
    return ~np.isnan(f0) & (db[k] >= thr)


def pitch_range(st: np.ndarray) -> float:
    return float(np.percentile(st, 90) - np.percentile(st, 10))


@dataclass(frozen=True)
class SegmentPitch:
    pitch_range_st: float | None  # p90 - p10 of voiced frames, semitones
    voiced_s: float  # seconds of voiced speech the range is measured on


def segment_pitch(
    st: np.ndarray, voiced: np.ndarray, hop_s: float, start: float, end: float, min_voiced_s: float
) -> SegmentPitch:
    a = max(0, int(np.ceil(start / hop_s - 1e-9)))
    b = max(0, int(np.ceil(end / hop_s - 1e-9)))
    seg = st[a:b][voiced[a:b]]
    voiced_s = round(len(seg) * hop_s, 2)
    if voiced_s < min_voiced_s:
        return SegmentPitch(None, voiced_s)
    return SegmentPitch(round(pitch_range(seg), 3), voiced_s)


__all__ = [
    "yin_f0",
    "to_semitones",
    "smooth_semitones",
    "voiced_mask",
    "pitch_range",
    "segment_pitch",
    "SegmentPitch",
]
