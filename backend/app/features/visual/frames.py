"""Tiny grayscale frame samples via ffmpeg (no OpenCV dependency). The source is only read."""

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.ingestion.probe import find_tool


def sample_frames(src: Path, cfg: dict[str, Any]) -> np.ndarray:
    """(n, height, width) uint8. Frame i is at t = i / sample_fps."""
    w, h, fps = cfg["width"], cfg["height"], cfg["sample_fps"]
    out = subprocess.run(
        [
            find_tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-an",
            "-sn",
            "-vf",
            f"fps={fps},scale={w}:{h}:flags=area,format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=1800,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg frame sampling failed: {out.stderr.decode()[-500:]}")
    n = len(out.stdout) // (w * h)
    return np.frombuffer(out.stdout[: n * w * h], dtype=np.uint8).reshape(n, h, w)
