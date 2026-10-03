import json

from fastapi import APIRouter, Depends, HTTPException

from backend.app import versions
from backend.app.abtest import ABRequest, ABResult, compare
from backend.app.deps import get_services
from backend.app.ingestion.probe import ToolMissing, find_tool
from backend.app.pipeline.runner import Services
from backend.app.schemas.job import Job
from backend.app.schemas.project import Language
from backend.app.settings import REPO_ROOT

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, svc: Services = Depends(get_services)) -> Job:
    job = svc.db.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.post("/ab-test", response_model=ABResult)
def post_ab_test(body: ABRequest, svc: Services = Depends(get_services)) -> ABResult:
    """Hook A/B simulator: two script versions compared in memory (nothing stored)."""
    if body.language == Language.ZH:
        raise HTTPException(422, "supported languages: en, hi, hinglish")
    return compare(body, svc.embedder)


@router.get("/validation")
def get_validation() -> dict:
    """Held-out validation of the current model (models/validation.json, written by training)."""
    path = REPO_ROOT / "models" / "validation.json"
    if not path.exists():
        raise HTTPException(404, "no validation report; run python scripts/train_model.py")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/health")
def health(svc: Services = Depends(get_services)) -> dict:
    from backend.app.gpu import cuda_device_count

    tools = {}
    for t in ("ffmpeg", "ffprobe"):
        try:
            tools[t] = find_tool(t)
        except ToolMissing:
            tools[t] = None
    return {
        "ok": svc.store is not None and all(tools.values()),
        "media_key_configured": svc.store is not None,
        "tools": tools,
        "cuda_devices": cuda_device_count(),
        "versions": {
            "app": versions.APP_VERSION,
            "transcript_schema": versions.TRANSCRIPT_SCHEMA_VERSION,
            "segmenter": versions.SEGMENTER_VERSION,
            "feature_schema": versions.FEATURE_SCHEMA_VERSION,
            "model": versions.MODEL_VERSION,
        },
    }
