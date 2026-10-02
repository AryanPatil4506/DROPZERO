"""SQLite records. Project/job metadata is stored as JSON; transcripts, segments and features
(derived from unpublished content) are stored encrypted as artifacts."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Float, LargeBinary, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.app.schemas.job import Job
from backend.app.schemas.project import Project
from backend.app.storage.media_store import decrypt_bytes, encrypt_bytes

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id() -> str:
    """ULID: 48-bit ms timestamp + 80 random bits, Crockford base32, sortable by creation."""
    n = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    return "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in reversed(range(26)))


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[str] = mapped_column(Text)


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[str] = mapped_column(Text)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)  # transcript|segments|text_features
    version: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float)
    blob: Mapped[bytes] = mapped_column(LargeBinary)  # encrypted JSON


class Database:
    def __init__(self, path: Path, key: bytes | None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.key = key

    # projects
    def save_project(self, p: Project) -> None:
        with Session(self.engine) as s, s.begin():
            s.merge(ProjectRow(id=p.id, data=p.model_dump_json()))

    def get_project(self, pid: str) -> Project | None:
        with Session(self.engine) as s:
            row = s.get(ProjectRow, pid)
            return Project.model_validate_json(row.data) if row else None

    def list_projects(self) -> list[Project]:
        with Session(self.engine) as s:
            rows = s.scalars(select(ProjectRow).order_by(ProjectRow.id.desc())).all()
            return [Project.model_validate_json(r.data) for r in rows]

    def delete_project(self, pid: str) -> None:
        with Session(self.engine) as s, s.begin():
            s.execute(delete(ArtifactRow).where(ArtifactRow.project_id == pid))
            s.execute(delete(JobRow).where(JobRow.project_id == pid))
            s.execute(delete(ProjectRow).where(ProjectRow.id == pid))

    # jobs
    def save_job(self, j: Job) -> None:
        with Session(self.engine) as s, s.begin():
            s.merge(JobRow(id=j.id, project_id=j.project_id, data=j.model_dump_json()))

    def get_job(self, jid: str) -> Job | None:
        with Session(self.engine) as s:
            row = s.get(JobRow, jid)
            return Job.model_validate_json(row.data) if row else None

    # encrypted artifacts
    def put_artifact(self, pid: str, kind: str, version: str, payload_json: str) -> None:
        if self.key is None:
            raise RuntimeError("media key required to store artifacts")
        blob = encrypt_bytes(self.key, payload_json.encode("utf-8"))
        with Session(self.engine) as s, s.begin():
            s.merge(
                ArtifactRow(
                    project_id=pid, kind=kind, version=version, created_at=time.time(), blob=blob
                )
            )

    def get_artifact(self, pid: str, kind: str) -> str | None:
        with Session(self.engine) as s:
            row = s.get(ArtifactRow, (pid, kind))
            if row is None:
                return None
            return decrypt_bytes(self.key, row.blob).decode("utf-8")

    def delete_artifacts(self, pid: str) -> None:
        with Session(self.engine) as s, s.begin():
            s.execute(delete(ArtifactRow).where(ArtifactRow.project_id == pid))
