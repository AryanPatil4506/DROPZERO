"""Timestamped ASR with faster-whisper (local, MIT-licensed weights).

Determinism: temperature 0 with no fallback, fixed beam size, no conditioning on previous text.
Results are cached (encrypted) by sha256(audio) + effective config, so re-analysing the same video
skips the model entirely.
"""

import json
import threading
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from backend.app.config import config_hash
from backend.app.gpu import ensure_cuda_libs, resolve_device
from backend.app.schemas.project import Language
from backend.app.schemas.transcript import TimingSource, Transcript, Word
from backend.app.segmentation.sentences import build_sentences
from backend.app.storage.media_store import decrypt_bytes, encrypt_bytes
from backend.app.versions import TRANSCRIPT_SCHEMA_VERSION

# One GPU job at a time.
GPU_LOCK = threading.Lock()


class AsrBackend(Protocol):
    def model_id(self) -> str: ...

    def effective_config(self) -> dict[str, Any]: ...

    def transcribe(self, audio: np.ndarray, language: str | None) -> dict[str, Any]:
        """Return faster-whisper-shaped JSON: {language, language_probability, duration,
        segments: [{start, end, text, words: [{word, start, end, probability}]}]}"""
        ...


class FasterWhisperBackend:
    def __init__(self, cfg: dict[str, Any], device_pref: str = "auto"):
        self.cfg = cfg
        self.device = resolve_device(device_pref)
        self.compute_type = cfg["compute_type"][self.device]
        self._model = None
        self._lock = threading.Lock()

    def model_id(self) -> str:
        return f"faster-whisper/{self.cfg['model']}@{self.compute_type}"

    def effective_config(self) -> dict[str, Any]:
        return {
            k: self.cfg[k]
            for k in (
                "model",
                "beam_size",
                "temperature",
                "condition_on_previous_text",
                "word_timestamps",
                "vad_filter",
                "vad_parameters",
            )
        } | {"compute_type": self.compute_type}

    def _load(self):
        with self._lock:
            if self._model is None:
                ensure_cuda_libs()
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.cfg["model"], device=self.device, compute_type=self.compute_type
                )
        return self._model

    def unload(self) -> None:
        """Free GPU memory (the explanation LLM shares the 8 GB card). Reloads on next use."""
        with self._lock:
            self._model = None

    def detect_language(self, audio: np.ndarray) -> tuple[str, float]:
        """Language of the first 30 s of audio: (code, probability)."""
        model = self._load()
        with GPU_LOCK:
            lang, prob, _ = model.detect_language(audio[: 30 * 16000])
        return lang, float(prob)

    def transcribe(self, audio: np.ndarray, language: str | None) -> dict[str, Any]:
        model = self._load()
        segs, info = model.transcribe(
            audio,
            language=language,
            beam_size=self.cfg["beam_size"],
            temperature=self.cfg["temperature"],
            condition_on_previous_text=self.cfg["condition_on_previous_text"],
            word_timestamps=self.cfg["word_timestamps"],
            vad_filter=self.cfg["vad_filter"],
            vad_parameters=self.cfg["vad_parameters"],
        )
        segments = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in (s.words or [])
                ],
            }
            for s in segs
        ]
        return {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": segments,
        }


def raw_to_transcript(
    raw: dict[str, Any],
    project_id: str,
    language: Language,
    duration_s: float,
    model_id: str | None,
    cfg_hash: str | None,
    sent_cfg: dict[str, Any],
) -> Transcript:
    words: list[Word] = []
    for seg in raw["segments"]:
        if words:
            words[-1].phrase_break = True  # previous Whisper segment ended
        for w in seg.get("words", []):
            text = w["word"].strip()
            if not text:
                continue
            start = round(float(w["start"]), 3)
            end = round(float(w["end"]), 3)
            if words:  # Whisper word times can overlap slightly; keep them monotonic
                start = max(start, words[-1].start)
            end = max(end, start)
            words.append(Word(text=text, start=start, end=end, confidence=w.get("probability")))
    confs = [w.confidence for w in words if w.confidence is not None]
    duration = round(max(duration_s, words[-1].end if words else 0.0), 3)
    return Transcript(
        project_id=project_id,
        language_declared=language,
        language_detected=raw.get("language"),
        language_prob=raw.get("language_probability"),
        timing_source=TimingSource.ASR,
        asr_model=model_id,
        asr_config_hash=cfg_hash,
        duration_s=duration,
        words=words,
        sentences=build_sentences(words, sent_cfg),
        mean_confidence=round(float(np.mean(confs)), 4) if confs else None,
        transcript_schema_version=TRANSCRIPT_SCHEMA_VERSION,
    )


def transcribe_cached(
    backend: AsrBackend,
    audio: np.ndarray,
    audio_sha: str,
    language: str | None,
    cache_dir: Path,
    key: bytes,
) -> tuple[dict[str, Any], str, bool]:
    """Returns (raw result, config hash, cache_hit)."""
    eff = backend.effective_config() | {"language": language, "model_id": backend.model_id()}
    h = config_hash(eff)
    path = cache_dir / "asr" / f"{config_hash([audio_sha, h])}.enc"
    if path.exists():
        return json.loads(decrypt_bytes(key, path.read_bytes())), h, True
    with GPU_LOCK:
        raw = backend.transcribe(audio, language)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(key, json.dumps(raw, ensure_ascii=False).encode("utf-8")))
    return raw, h, False
