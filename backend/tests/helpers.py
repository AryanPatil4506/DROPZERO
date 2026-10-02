"""Test doubles. Deterministic and offline; never used by the app itself."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.features.text.lexical import tokens

FIX = Path(__file__).parent / "fixtures"


def load_raw(lang: str) -> dict[str, Any]:
    return json.loads((FIX / f"asr_{lang}.json").read_text(encoding="utf-8"))


class HashingEmbedder:
    """Bag-of-words hashed into 256 dims. Lexical only — enough to test feature *logic*
    (identical/overlapping text scores high), not semantic quality."""

    dim = 256

    def model_id(self) -> str:
        return "test/hashing-bow-256"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokens(t):
                h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:4], "big")
                out[i, h % self.dim] += 1.0
            n = np.linalg.norm(out[i])
            if n > 0:
                out[i] /= n
            else:
                out[i, 0] = 1.0
        return out


class FixtureAsr:
    """Returns a fixture's faster-whisper-shaped JSON; counts calls."""

    def __init__(self, lang: str):
        self.lang = lang
        self.calls = 0

    def model_id(self) -> str:
        return "fixture/asr"

    def effective_config(self) -> dict[str, Any]:
        return {"fixture": self.lang}

    def transcribe(self, audio: np.ndarray, language: str | None) -> dict[str, Any]:
        self.calls += 1
        return load_raw(self.lang)
