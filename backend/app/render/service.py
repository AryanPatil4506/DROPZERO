"""Background rendering of edit plans.

The edited copy is stored like the original: encrypted in the media store as
`render-<plan key>`, streamed with HTTP Range, purged on the same retention schedule (it lives in
the project's media folder). The decrypted working copy exists only in a per-render work dir that
is always deleted. The same plan is rendered once and then served from the store.
"""

import logging
import shutil
import threading
import time
from typing import Literal

from pydantic import BaseModel

from backend.app.config import load_config
from backend.app.pipeline.runner import Services
from backend.app.render.ffmpeg import render
from backend.app.render.plan import RenderPlan
from backend.app.storage.db import new_id

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "done", "failed"]


class RenderStatus(BaseModel):
    render_id: str
    status: Status
    error: str | None = None
    encoder: str | None = None
    seconds: float | None = None
    plan: RenderPlan | None = None


_lock = threading.Lock()
_state: dict[tuple[str, str], RenderStatus] = {}
_gpu = threading.Lock()  # one render at a time (shares the GPU with analysis)


def name_for(render_id: str) -> str:
    return f"render-{render_id}"


def status(svc: Services, pid: str, render_id: str) -> RenderStatus | None:
    with _lock:
        st = _state.get((pid, render_id))
    if st is not None:
        return st
    if svc.store is not None and svc.store.exists(pid, name_for(render_id)):
        return RenderStatus(render_id=render_id, status="done")  # rendered before a restart
    return None


def submit(svc: Services, pid: str, plan: RenderPlan) -> tuple[RenderStatus, bool]:
    """Register a render. Returns (status, needs_run)."""
    rid = plan.key()
    with _lock:
        cur = _state.get((pid, rid))
        if cur is not None and cur.status in ("queued", "running", "done"):
            return cur, False
        if svc.store is not None and svc.store.exists(pid, name_for(rid)):
            st = RenderStatus(render_id=rid, status="done", plan=plan)
            _state[(pid, rid)] = st
            return st, False
        st = RenderStatus(render_id=rid, status="queued", plan=plan)
        _state[(pid, rid)] = st
        return st, True


def run(svc: Services, pid: str, plan: RenderPlan, has_audio: bool) -> None:
    rid = plan.key()
    cfg = load_config("render")
    work = svc.settings.work_dir / f"render-{new_id()}"
    t0 = time.time()
    with _gpu:
        _set(pid, rid, status="running")
        try:
            work.mkdir(parents=True, exist_ok=True)
            src = work / "source.mp4"
            out = work / "edited.mp4"
            svc.store.decrypt_to(pid, "original", src)
            encoder = render(src, out, plan.pieces, has_audio, cfg)
            svc.store.put_file(pid, name_for(rid), out)
            _set(pid, rid, status="done", encoder=encoder, seconds=round(time.time() - t0, 1))
        except Exception as e:  # noqa: BLE001 - surfaced to the UI verbatim
            log.exception("render failed")
            _set(pid, rid, status="failed", error=str(e)[:800])
        finally:
            shutil.rmtree(work, ignore_errors=True)


def forget(pid: str) -> None:
    """Drop status records of a deleted project."""
    with _lock:
        for k in [k for k in _state if k[0] == pid]:
            del _state[k]


def _set(pid: str, rid: str, **kw) -> None:
    with _lock:
        cur = _state.get((pid, rid)) or RenderStatus(render_id=rid, status="queued")
        _state[(pid, rid)] = cur.model_copy(update=kw)
