import hashlib
import subprocess
import wave
from pathlib import Path

import numpy as np

from backend.app.ingestion.probe import find_tool

SAMPLE_RATE = 16000


def extract_audio(src: Path, dest_wav: Path) -> None:
    """16 kHz mono PCM WAV via ffmpeg. The source file is only read."""
    out = subprocess.run(
        [
            find_tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(dest_wav),
        ],
        capture_output=True,
        check=False,
        timeout=1800,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {out.stderr.decode()[-500:]}")


def load_wav(path: Path) -> np.ndarray:
    """Float32 mono samples in [-1, 1]. Avoids PyAV entirely."""
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("expected 16 kHz mono 16-bit WAV")
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def audio_sha256(samples: np.ndarray) -> str:
    return hashlib.sha256(samples.tobytes()).hexdigest()
