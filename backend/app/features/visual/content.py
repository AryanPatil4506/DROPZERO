"""What is on screen: frame-wise visual content type and how well the picture matches the speech.

Frames are sampled at `content.sample_fps` (colour, letterboxed to a square so slide edges are kept)
and embedded with CLIP (open weights, local). Each frame gets the closest of a fixed list of content
types from config ("slide with text", "diagram", "talking head", ...), zero-shot, so the same frames
always give the same labels. Speech match = cosine between a segment's frames and its transcript
text, using CLIP's multilingual text encoder (English, Hindi, Hinglish), judged against this
video's own median.

Supporting evidence only: DROPZERO's retention model was trained without frames (no video exists
for the training lectures), so nothing here is validated against retention data.
"""

import logging
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from backend.app.ingestion.probe import find_tool

log = logging.getLogger(__name__)


def sample_rgb_frames(src: Path, cfg: dict[str, Any]) -> np.ndarray:
    """(n, size, size, 3) uint8. Frame i is at t = i / sample_fps. The source is only read."""
    s, fps = cfg["size"], cfg["sample_fps"]
    vf = (
        f"fps={fps},scale={s}:{s}:force_original_aspect_ratio=decrease:flags=area,"
        f"pad={s}:{s}:(ow-iw)/2:(oh-ih)/2,format=rgb24"
    )
    out = subprocess.run(
        [find_tool("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(src)]
        + ["-an", "-sn", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True,
        check=False,
        timeout=1800,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg frame sampling failed: {out.stderr.decode()[-500:]}")
    per = s * s * 3
    n = len(out.stdout) // per
    return np.frombuffer(out.stdout[: n * per], dtype=np.uint8).reshape(n, s, s, 3)


class VisualEncoder(Protocol):
    def model_id(self) -> str: ...

    def embed_images(self, frames: np.ndarray) -> np.ndarray:
        """(n, d) L2-normalised image embeddings."""
        ...

    def embed_labels(self, texts: list[str]) -> np.ndarray:
        """(n, d) L2-normalised English prompt embeddings (CLIP's own text encoder)."""
        ...

    def embed_speech(self, texts: list[str]) -> np.ndarray:
        """(n, d) L2-normalised multilingual text embeddings in the same space as the images."""
        ...


class ClipEncoder:
    """sentence-transformers CLIP: image + English text model, plus the multilingual text model
    distilled into the same embedding space."""

    def __init__(self, cfg: dict[str, Any], device_pref: str = "auto"):
        self.cfg = cfg
        self.device_pref = device_pref
        self._img = self._txt = None
        self._lock = threading.Lock()

    def model_id(self) -> str:
        return f"{self.cfg['image_model']}+{self.cfg['text_model']}"

    def _load(self):
        with self._lock:
            if self._img is None:
                import torch
                from sentence_transformers import SentenceTransformer

                device = self.device_pref
                if device == "auto":
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                self._img = SentenceTransformer(self.cfg["image_model"], device=device)
                self._txt = SentenceTransformer(self.cfg["text_model"], device=device)
        return self._img, self._txt

    def embed_images(self, frames: np.ndarray) -> np.ndarray:
        from PIL import Image

        img, _ = self._load()
        pics = [Image.fromarray(f) for f in frames]
        return img.encode(pics, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)

    def embed_labels(self, texts: list[str]) -> np.ndarray:
        img, _ = self._load()
        return img.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    def embed_speech(self, texts: list[str]) -> np.ndarray:
        _, txt = self._load()
        return txt.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def label_matrix(enc: VisualEncoder, types: list[dict[str, Any]]) -> np.ndarray:
    """(k, d): mean of each type's prompt embeddings, re-normalised."""
    rows = []
    for t in types:
        e = enc.embed_labels(t["prompts"]).mean(axis=0)
        rows.append(e / (np.linalg.norm(e) + 1e-12))
    return np.stack(rows)


def classify_frames(
    img_emb: np.ndarray, labels: np.ndarray, keys: list[str], temperature: float, min_conf: float
) -> tuple[list[str], np.ndarray]:
    """Per frame: the closest content type ("unclear" below min_conf) and its softmax confidence."""
    if len(img_emb) == 0:
        return [], np.zeros(0)
    logits = temperature * img_emb @ labels.T
    logits -= logits.max(axis=1, keepdims=True)
    p = np.exp(logits)
    p /= p.sum(axis=1, keepdims=True)
    best = p.argmax(axis=1)
    conf = p[np.arange(len(p)), best]
    return [keys[b] if c >= min_conf else "unclear" for b, c in zip(best, conf, strict=True)], conf


@dataclass(frozen=True)
class Run:
    start: float
    end: float
    label: str


def label_runs(labels: list[str], fps: float, min_run_s: float) -> list[Run]:
    """Consecutive frames with the same label; runs shorter than min_run_s merge into the
    previous run (one odd frame does not split a 40 s slide)."""
    runs: list[Run] = []
    for i, lab in enumerate(labels):
        t0, t1 = i / fps, (i + 1) / fps
        if runs and runs[-1].label == lab:
            runs[-1] = Run(runs[-1].start, t1, lab)
        else:
            runs.append(Run(t0, t1, lab))
    merged: list[Run] = []
    for r in runs:
        if merged and (r.end - r.start < min_run_s or r.label == merged[-1].label):
            merged[-1] = Run(merged[-1].start, r.end, merged[-1].label)
        else:
            merged.append(r)
    if len(merged) > 1 and merged[0].end - merged[0].start < min_run_s:
        merged[1] = Run(0.0, merged[1].end, merged[1].label)
        merged.pop(0)
    return [Run(round(r.start, 2), round(r.end, 2), r.label) for r in merged]


@dataclass(frozen=True)
class SegmentContent:
    visual_type: str | None  # most common frame label in the segment
    visual_type_share: float | None  # share of the segment's frames with that label
    speech_match: float | None  # mean cosine of the segment's frames with its text


def segment_content(
    labels: list[str],
    img_emb: np.ndarray,
    speech_emb: np.ndarray | None,
    fps: float,
    start: float,
    end: float,
) -> SegmentContent:
    a, b = int(np.ceil(start * fps - 1e-9)), int(np.ceil(end * fps - 1e-9))
    labs = labels[a:b]
    if not labs:
        return SegmentContent(None, None, None)
    vals, counts = np.unique(labs, return_counts=True)
    k = int(np.argmax(counts))  # np.unique sorts, so ties resolve alphabetically (deterministic)
    match = None
    if speech_emb is not None:
        match = round(float((img_emb[a:b] @ speech_emb).mean()), 4)
    return SegmentContent(str(vals[k]), round(float(counts[k] / len(labs)), 3), match)


__all__ = [
    "sample_rgb_frames",
    "VisualEncoder",
    "ClipEncoder",
    "label_matrix",
    "classify_frames",
    "label_runs",
    "Run",
    "segment_content",
    "SegmentContent",
]
