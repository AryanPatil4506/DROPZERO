import hashlib
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.app.config import load_config
from backend.app.deps import get_services
from backend.app.ingestion.probe import ToolMissing, probe
from backend.app.ingestion.validate import (
    ValidationError,
    check_video_header,
    decode_script,
    duration_warnings,
)
from backend.app.pipeline.runner import Services, new_job, run_job
from backend.app.schemas.av_features import AVFeatureSet
from backend.app.schemas.features import TextFeatureSet
from backend.app.schemas.flags import FlagsResponse
from backend.app.schemas.job import Job
from backend.app.schemas.prediction import Prediction
from backend.app.schemas.project import Project, ProjectCreate, ProjectStatus, SourceType
from backend.app.schemas.segment import Segment
from backend.app.schemas.transcript import Transcript
from backend.app.simulate.edits import Simulation, simulate
from backend.app.storage.db import new_id, utcnow

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project(svc: Services, pid: str) -> Project:
    p = svc.db.get_project(pid)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


def _require_store(svc: Services):
    if svc.store is None:
        raise HTTPException(
            503, "DROPZERO_MEDIA_KEY is not configured; run scripts/gen_key.py (see README)"
        )
    return svc.store


def _reset_for_new_source(svc: Services, p: Project) -> None:
    svc.db.delete_artifacts(p.id)
    p.warnings = []
    p.media = None
    p.duration_s = None
    p.status = ProjectStatus.UPLOADED
    p.uploaded_at = utcnow()


@router.post("", response_model=Project, status_code=201)
def create_project(body: ProjectCreate, svc: Services = Depends(get_services)) -> Project:
    p = Project(id=new_id(), created_at=utcnow(), **body.model_dump())
    svc.db.save_project(p)
    return p


@router.get("", response_model=list[Project])
def list_projects(svc: Services = Depends(get_services)) -> list[Project]:
    return svc.db.list_projects()


@router.get("/{pid}", response_model=Project)
def get_project(pid: str, svc: Services = Depends(get_services)) -> Project:
    return _project(svc, pid)


@router.post("/{pid}/video", response_model=Project)
def upload_video(pid: str, file: UploadFile, svc: Services = Depends(get_services)) -> Project:
    p = _project(svc, pid)
    store = _require_store(svc)
    name = file.filename or "upload"
    head = file.file.read(16)
    try:
        check_video_header(head, name)
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e

    limit = load_config("ingestion")["max_upload_bytes"]
    tmp_dir = svc.settings.work_dir / f"upload-{new_id()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        tmp = tmp_dir / f"source{Path(name).suffix.lower()}"
        size = len(head)
        with tmp.open("wb") as out:
            out.write(head)
            while block := file.file.read(1 << 20):
                size += len(block)
                if size > limit:
                    raise HTTPException(413, "file too large")
                out.write(block)
        try:
            info = probe(tmp)
        except ToolMissing as e:
            raise HTTPException(503, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if not info.has_audio:
            raise HTTPException(422, "video has no audio track; DROPZERO needs speech")
        try:
            warnings = duration_warnings(info.duration_s)
        except ValidationError as e:
            raise HTTPException(422, str(e)) from e
        sha, _ = store.put_file(pid, "original", tmp)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    _reset_for_new_source(svc, p)
    p.source_type = SourceType.VIDEO
    p.media = info
    p.duration_s = info.duration_s
    p.warnings = warnings
    p.source_sha256 = sha
    p.source_filename = Path(name).name
    svc.db.save_project(p)
    return p


@router.post("/{pid}/script", response_model=Project)
async def upload_script(
    pid: str, request: Request, svc: Services = Depends(get_services)
) -> Project:
    """Multipart form with `file` (TXT/MD), or JSON {"text": "..."}."""
    p = _project(svc, pid)
    store = _require_store(svc)
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        body = json.loads(await request.body() or b"{}")
        if not isinstance(body.get("text"), str):
            raise HTTPException(422, 'expected JSON {"text": "..."}')
        data, name = body["text"].encode("utf-8"), "script.txt"
    else:
        form = await request.form()
        f = form.get("file")
        if f is None or isinstance(f, str):
            raise HTTPException(422, "expected a multipart `file` field")
        data, name = await f.read(), f.filename or "script.txt"
    try:
        text = decode_script(data, name)
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e
    encoded = text.encode("utf-8")
    store.put_bytes(pid, "script", encoded)
    store.path(pid, "original").unlink(missing_ok=True)

    _reset_for_new_source(svc, p)
    p.source_type = SourceType.SCRIPT
    p.source_sha256 = hashlib.sha256(data).hexdigest()
    p.source_filename = Path(name).name
    svc.db.save_project(p)
    return p


@router.post("/{pid}/analyze", response_model=Job, status_code=202)
def analyze(pid: str, bg: BackgroundTasks, svc: Services = Depends(get_services)) -> Job:
    p = _project(svc, pid)
    _require_store(svc)
    if p.source_type is None:
        raise HTTPException(409, "upload a video or script first")
    if p.status == ProjectStatus.PROCESSING:
        raise HTTPException(409, "analysis already running")
    job = new_job(new_id(), p)
    svc.db.save_job(job)
    p.status = ProjectStatus.PROCESSING
    svc.db.save_project(p)
    bg.add_task(run_job, svc, job.id)
    return job


def _artifact(svc: Services, pid: str, kind: str) -> str:
    _project(svc, pid)
    raw = svc.db.get_artifact(pid, kind)
    if raw is None:
        raise HTTPException(404, f"no {kind} yet; run analyze")
    return raw


@router.get("/{pid}/transcript", response_model=Transcript)
def get_transcript(pid: str, svc: Services = Depends(get_services)) -> Transcript:
    return Transcript.model_validate_json(_artifact(svc, pid, "transcript"))


@router.get("/{pid}/segments", response_model=list[Segment])
def get_segments(pid: str, svc: Services = Depends(get_services)) -> list[Segment]:
    return [Segment.model_validate(s) for s in json.loads(_artifact(svc, pid, "segments"))]


@router.get("/{pid}/features/text", response_model=TextFeatureSet)
def get_text_features(pid: str, svc: Services = Depends(get_services)) -> TextFeatureSet:
    return TextFeatureSet.model_validate_json(_artifact(svc, pid, "text_features"))


@router.get("/{pid}/features/av", response_model=AVFeatureSet)
def get_av_features(pid: str, svc: Services = Depends(get_services)) -> AVFeatureSet:
    if _project(svc, pid).source_type == SourceType.SCRIPT:
        raise HTTPException(404, "audio/visual features need a video upload (script mode)")
    return AVFeatureSet.model_validate_json(_artifact(svc, pid, "av_features"))


@router.get("/{pid}/prediction", response_model=Prediction)
def get_prediction(pid: str, svc: Services = Depends(get_services)) -> Prediction:
    return Prediction.model_validate_json(_artifact(svc, pid, "prediction"))


@router.get("/{pid}/flags", response_model=FlagsResponse)
def get_flags(pid: str, svc: Services = Depends(get_services)) -> FlagsResponse:
    return FlagsResponse.model_validate_json(_artifact(svc, pid, "flags"))


class SimulateRequest(BaseModel):
    edit_ids: list[str]


@router.post("/{pid}/simulate", response_model=Simulation)
def post_simulate(
    pid: str, body: SimulateRequest, svc: Services = Depends(get_services)
) -> Simulation:
    t = Transcript.model_validate_json(_artifact(svc, pid, "transcript"))
    flags = FlagsResponse.model_validate_json(_artifact(svc, pid, "flags"))
    pred = Prediction.model_validate_json(_artifact(svc, pid, "prediction"))
    unknown = set(body.edit_ids) - {e.id for e in flags.edits}
    if unknown or not body.edit_ids:
        raise HTTPException(422, f"unknown or empty edit ids: {sorted(unknown)}")
    cfgs = {k: load_config(k) for k in ("segmentation", "text_features", "fillers")}
    return simulate(t, flags.edits, body.edit_ids, pred.points, svc.embedder, cfgs)


@router.delete("/{pid}", status_code=204)
def delete_project(pid: str, svc: Services = Depends(get_services)) -> None:
    _project(svc, pid)
    if svc.store is not None:
        svc.store.delete_project(pid)
    svc.db.delete_project(pid)
