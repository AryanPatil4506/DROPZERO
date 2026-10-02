from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    id: str
    project_id: str
    status: JobStatus = JobStatus.QUEUED
    stages: list[str]
    stage: str | None = None
    progress: float = 0.0  # 0..1, advances per completed stage
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
