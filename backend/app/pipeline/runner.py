"""Analysis pipeline: stages with job progress.

Decrypted media only ever exists inside work/<job_id>/, which is deleted when the job ends,
including on failure.
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.config import load_config
from backend.app.detection.flags import detect, promise_check
from backend.app.detection.promises import build_ledger
from backend.app.features.av import detect_cuts, extract_av_features
from backend.app.features.text.embedder import Embedder, SentenceTransformerEmbedder
from backend.app.features.text.extract import extract_text_features
from backend.app.features.visual.frames import sample_frames
from backend.app.ingestion.audio import audio_sha256, extract_audio, load_wav
from backend.app.model.predict import predict
from backend.app.schemas.job import Job, JobStatus
from backend.app.schemas.project import Project, ProjectStatus, SourceType
from backend.app.schemas.segment import Segment
from backend.app.schemas.transcript import Transcript
from backend.app.segmentation.windows import segment_transcript
from backend.app.settings import Settings
from backend.app.storage.db import Database, utcnow
from backend.app.storage.media_store import MediaStore
from backend.app.transcription.asr import (
    AsrBackend,
    FasterWhisperBackend,
    raw_to_transcript,
    transcribe_cached,
)
from backend.app.transcription.script_timing import estimate_transcript
from backend.app.versions import (
    AV_FEATURE_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    SEGMENTER_VERSION,
    TRANSCRIPT_SCHEMA_VERSION,
)

log = logging.getLogger("dropzero.pipeline")

VIDEO_STAGES = [
    "extract_media",
    "transcribe",
    "segment",
    "text_features",
    "av_features",
    "predict",
    "detect",
]
SCRIPT_STAGES = ["estimate_timing", "segment", "text_features", "predict", "detect"]


@dataclass
class Services:
    settings: Settings
    db: Database
    store: MediaStore | None  # None when no media key is configured
    key: bytes | None
    _asr: AsrBackend | None = None
    _embedder: Embedder | None = None
    _llm: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def asr(self) -> AsrBackend:
        if self._asr is None:
            self._asr = FasterWhisperBackend(load_config("asr"), self.settings.asr_device)
        return self._asr

    @property
    def llm(self):
        if self._llm is None:
            from backend.app.explain.llm import LocalLLM

            self._llm = LocalLLM(load_config("llm"))
        return self._llm

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = SentenceTransformerEmbedder(
                load_config("text_features")["embedding"], self.settings.embed_device
            )
        return self._embedder


def stages_for(project: Project) -> list[str]:
    return VIDEO_STAGES if project.source_type == SourceType.VIDEO else SCRIPT_STAGES


def script_warnings(duration_s: float) -> list[str]:
    cfg = load_config("ingestion")
    if cfg["recommended_min_s"] <= duration_s <= cfg["recommended_max_s"]:
        return []
    return [
        f"Estimated spoken length {duration_s / 60:.1f} min is outside the tested 5–15 min "
        "range; results may be less reliable."
    ]


def run_job(svc: Services, job_id: str) -> None:
    job = svc.db.get_job(job_id)
    project = svc.db.get_project(job.project_id)
    work: Path = svc.settings.work_dir / job_id
    work.mkdir(parents=True, exist_ok=True)
    ctx: dict[str, Any] = {}
    try:
        job.status = JobStatus.RUNNING
        svc.db.save_job(job)
        for k, stage in enumerate(job.stages):
            job.stage = stage
            svc.db.save_job(job)
            _STAGES[stage](svc, project, work, ctx)
            job.progress = round((k + 1) / len(job.stages), 3)
            svc.db.save_job(job)
        project.status = ProjectStatus.READY
        job.status = JobStatus.DONE
        job.stage = None
    except Exception as e:  # report every failure on the job; never leave it "running"
        log.exception("job %s failed at %s", job_id, job.stage)
        job.status = JobStatus.FAILED
        job.error = f"{type(e).__name__}: {e}"
        project.status = ProjectStatus.FAILED
    finally:
        shutil.rmtree(work, ignore_errors=True)
        job.finished_at = utcnow()
        svc.db.save_job(job)
        svc.db.save_project(project)


def _extract_media(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    """Decrypt once, pull audio + tiny frame samples, delete the decrypted copy immediately."""
    src = work / f"source{Path(p.source_filename or 'x.mp4').suffix.lower()}"
    svc.store.decrypt_to(p.id, "original", src)
    wav = work / "audio.wav"
    av_cfg = load_config("av_features")
    has_video = bool(p.media and p.media.has_video)
    try:
        extract_audio(src, wav)
        frames = sample_frames(src, av_cfg["visual"]) if has_video else None
    finally:
        src.unlink(missing_ok=True)
    ctx["audio"] = load_wav(wav)
    wav.unlink(missing_ok=True)
    ctx["has_video"] = has_video
    ctx["diffs"], ctx["scene_cuts"] = detect_cuts(frames, av_cfg)


def _transcribe(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    audio = ctx["audio"]
    lang = load_config("asr")["language_map"][p.language.value]
    raw, h, hit = transcribe_cached(
        svc.asr, audio, audio_sha256(audio), lang, svc.settings.cache_dir, svc.key
    )
    log.info("ASR %s for project %s", "cache hit" if hit else "ran", p.id)
    if hasattr(svc.asr, "unload"):
        svc.asr.unload()
    t = raw_to_transcript(
        raw,
        p.id,
        p.language,
        p.duration_s or 0.0,
        svc.asr.model_id(),
        h,
        load_config("segmentation")["sentences"],
    )
    _store_transcript(svc, t, ctx)


def _estimate_timing(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    text = svc.store.get_bytes(p.id, "script").decode("utf-8")
    seg_cfg = load_config("segmentation")
    t = estimate_transcript(text, p.id, p.language, seg_cfg["script_timing"], seg_cfg["sentences"])
    p.duration_s = t.duration_s
    p.warnings = script_warnings(t.duration_s)
    _store_transcript(svc, t, ctx)


def _store_transcript(svc: Services, t: Transcript, ctx: dict) -> None:
    svc.db.put_artifact(t.project_id, "transcript", TRANSCRIPT_SCHEMA_VERSION, t.model_dump_json())
    ctx["transcript"] = t


def _segment(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    segs = segment_transcript(
        ctx["transcript"],
        load_config("segmentation")["windows"],
        boundary_hints=ctx.get("scene_cuts"),
    )
    payload = json.dumps([s.model_dump(mode="json") for s in segs], ensure_ascii=False)
    svc.db.put_artifact(p.id, "segments", SEGMENTER_VERSION, payload)
    ctx["segments"] = segs


def _text_features(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    segs: list[Segment] = ctx["segments"]
    fs = extract_text_features(
        ctx["transcript"], segs, svc.embedder, load_config("text_features"), load_config("fillers")
    )
    svc.db.put_artifact(p.id, "text_features", FEATURE_SCHEMA_VERSION, fs.model_dump_json())
    ctx["text_features"] = fs


def _predict(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    t = ctx["transcript"]
    pred = predict(ctx["segments"], ctx["text_features"], t.duration_s)
    svc.db.put_artifact(p.id, "prediction", pred.model_version, pred.model_dump_json())
    ctx["prediction"] = pred


def _detect(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    cfg = load_config("detection")
    t = ctx["transcript"]
    promise = promise_check(p.title, t, svc.embedder, cfg["promise"])
    av = ctx.get("av_features")
    ledger = build_ledger(t, promise, svc.embedder, load_config("promises"))
    res = detect(
        t, ctx["segments"], ctx["text_features"], ctx["prediction"], promise, cfg, av, ledger
    )
    svc.db.put_artifact(p.id, "flags", res.rules_version, res.model_dump_json())


def _av_features(svc: Services, p: Project, work: Path, ctx: dict) -> None:
    fs = extract_av_features(
        p.id,
        ctx["segments"],
        ctx.pop("audio"),
        ctx["diffs"],
        ctx["scene_cuts"],
        ctx["has_video"],
        load_config("av_features"),
    )
    svc.db.put_artifact(p.id, "av_features", AV_FEATURE_SCHEMA_VERSION, fs.model_dump_json())
    ctx["av_features"] = fs


_STAGES = {
    "extract_media": _extract_media,
    "av_features": _av_features,
    "predict": _predict,
    "detect": _detect,
    "transcribe": _transcribe,
    "estimate_timing": _estimate_timing,
    "segment": _segment,
    "text_features": _text_features,
}


def new_job(job_id: str, project: Project) -> Job:
    return Job(id=job_id, project_id=project.id, stages=stages_for(project), created_at=utcnow())
