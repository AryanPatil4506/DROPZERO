import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session

from backend.app.api import jobs, projects
from backend.app.deps import get_services
from backend.app.schemas.job import JobStatus
from backend.app.schemas.project import ProjectStatus
from backend.app.storage.db import JobRow, utcnow
from backend.app.versions import APP_VERSION

log = logging.getLogger("dropzero")


def startup_housekeeping(app: FastAPI) -> None:
    svc = app.dependency_overrides.get(get_services, get_services)()
    # work dirs only hold decrypted media of running jobs; anything left is from a crash
    if svc.settings.work_dir.exists():
        shutil.rmtree(svc.settings.work_dir, ignore_errors=True)
    if svc.store is not None:
        purged = svc.store.purge_older_than(svc.settings.media_retention_hours)
        if purged:
            log.info("purged media for %d project(s)", len(purged))
    # jobs interrupted by a restart can never finish
    with Session(svc.db.engine) as s:
        ids = [r.id for r in s.query(JobRow).all()]
    for jid in ids:
        job = svc.db.get_job(jid)
        if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            job.status, job.error, job.finished_at = JobStatus.FAILED, "server restarted", utcnow()
            svc.db.save_job(job)
            p = svc.db.get_project(job.project_id)
            if p and p.status == ProjectStatus.PROCESSING:
                p.status = ProjectStatus.FAILED
                svc.db.save_project(p)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_housekeeping(app)
    yield


app = FastAPI(title="DROPZERO", version=APP_VERSION, lifespan=lifespan)
app.include_router(projects.router)
app.include_router(jobs.router)
