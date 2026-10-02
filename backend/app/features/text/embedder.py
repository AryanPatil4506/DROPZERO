"""Local multilingual sentence embeddings (open weights, run on this machine; no API calls)."""

import threading
from typing import Any, Protocol

import numpy as np


class Embedder(Protocol):
    def model_id(self) -> str: ...

    def embed(self, texts: list[str]) -> np.ndarray:
        """(n, d) float32, L2-normalised. Deterministic for the same input."""
        ...


class SentenceTransformerEmbedder:
    def __init__(self, cfg: dict[str, Any], device_pref: str = "auto"):
        self.cfg = cfg
        self.device_pref = device_pref
        self._model = None
        self._lock = threading.Lock()

    def model_id(self) -> str:
        return self.cfg["model"]

    def _load(self):
        with self._lock:
            if self._model is None:
                import torch
                from sentence_transformers import SentenceTransformer

                device = self.device_pref
                if device == "auto":
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
                self._model = SentenceTransformer(self.cfg["model"], device=device)
                self._model.max_seq_length = self.cfg["max_seq_length"]
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        model = self._load()
        prefix = self.cfg.get("prefix") or ""
        vecs = model.encode(
            [prefix + t for t in texts],
            batch_size=self.cfg["batch_size"],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32)
