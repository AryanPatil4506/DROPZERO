"""Before/after render: plan building (pure) and a real ffmpeg render of a generated clip."""

import subprocess

import pytest

from backend.app.config import load_config
from backend.app.ingestion import probe as probe_mod
from backend.app.render import service as render_service
from backend.app.render.ffmpeg import _atempo, build_filter
from backend.app.render.plan import Piece, build_plan
from backend.app.schemas.flags import Edit
from backend.app.simulate.exposure import CustomEdit


def _edit(i, action, start, end, target=None, simulatable=True):
    return Edit(
        id=i,
        flag_id="f",
        action=action,
        start=start,
        end=end,
        target_time=target,
        reason="r",
        simulatable=simulatable,
    )


def test_cut_and_speed_pieces():
    edits = [_edit("e1", "CUT", 10, 20)]
    custom = [CustomEdit(action="SPEED", start=30, end=40, factor=2.0)]
    plan = build_plan(edits, ["e1"], custom, 60.0)
    assert [(p.start, p.end, p.factor) for p in plan.pieces] == [
        (0, 10, 1.0),
        (20, 30, 1.0),
        (30, 40, 2.0),
        (40, 60, 1.0),
    ]
    assert plan.output_duration_s == pytest.approx(10 + 10 + 5 + 20)
    assert plan.applied_edit_ids == ["e1"] and plan.applied_custom == custom


def test_trims_match_the_simulator():
    custom = [
        CustomEdit(action="TRIM_START", start=0, end=5),
        CustomEdit(action="TRIM_END", start=50, end=60),
    ]
    plan = build_plan([], [], custom, 60.0)
    assert [(p.start, p.end) for p in plan.pieces] == [(5, 50)]


def test_move_reorders_before_target():
    # move the demo (40-50) to just before 10
    edits = [_edit("m1", "MOVE", 40, 50, target=10, simulatable=False)]
    plan = build_plan(edits, ["m1"], [], 60.0)
    assert [(p.start, p.end) for p in plan.pieces] == [(0, 10), (40, 50), (10, 40), (50, 60)]
    assert plan.moved_edit_ids == ["m1"] and "m1" not in plan.skipped_edit_ids
    assert plan.output_duration_s == pytest.approx(60.0)


def test_move_into_itself_is_skipped_and_slivers_dropped():
    edits = [_edit("m1", "MOVE", 10, 20, target=15), _edit("c1", "CUT", 0.0, 59.9)]
    plan = build_plan(edits, ["m1", "c1"], [], 60.0)
    assert plan.moved_edit_ids == [] and plan.pieces == []  # 0.1 s left is below min_piece_s


def test_plan_key_is_stable_and_plan_specific():
    a = build_plan([_edit("e1", "CUT", 10, 20)], ["e1"], [], 60.0)
    b = build_plan([_edit("e1", "CUT", 10, 20)], ["e1"], [], 60.0)
    c = build_plan([_edit("e1", "CUT", 10, 21)], ["e1"], [], 60.0)
    assert a.key() == b.key() != c.key()


def test_filter_graph():
    assert _atempo(1.0) == "" and _atempo(1.5) == "atempo=1.500000"
    assert _atempo(3.0) == "atempo=2.0,atempo=1.500000"
    g = build_filter([Piece(start=0, end=5), Piece(start=8, end=10, factor=2.0)], True, 720, 15)
    assert "trim=start=8.000:end=10.000,setpts=(PTS-STARTPTS)/2.000000" in g
    assert "afade=t=out" in g and "concat=n=2:v=1:a=1[vc][ac]" in g
    assert "min(720,ih)" in g
    assert "[a0]" not in build_filter([Piece(start=0, end=5)], False, 720, 15)


def _ffmpeg():
    try:
        return probe_mod.find_tool("ffmpeg")
    except probe_mod.ToolMissing:
        return None


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg not installed")
def test_real_render_and_api(tmp_path, settings, monkeypatch):
    """Render a generated 20 s clip with a cut, a 2x speed-up and a move; check the result length,
    that it is stored encrypted, and that the API serves it with Range."""
    from fastapi.testclient import TestClient

    from backend.app.deps import build_services, get_services
    from backend.app.main import app
    from backend.app.schemas.flags import FlagsResponse, PromiseCheck

    src = tmp_path / "clip.mp4"
    subprocess.run(
        [
            _ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=20",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=20",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src),
        ],
        check=True,
        timeout=120,
    )  # fmt: skip
    svc = build_services(settings)
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with TestClient(app) as c:
            pid = c.post(
                "/api/projects", json={"title": "Render test", "category": "tech", "language": "en"}
            ).json()["id"]
            with src.open("rb") as f:
                r = c.post(f"/api/projects/{pid}/video", files={"file": ("clip.mp4", f)})
            # duration rules reject a 20 s clip for analysis; rendering doesn't need it
            if r.status_code != 200:
                monkeypatch.setattr(
                    "backend.app.api.projects.duration_warnings", lambda d: ["short test clip"]
                )
                with src.open("rb") as f:
                    r = c.post(f"/api/projects/{pid}/video", files={"file": ("clip.mp4", f)})
            assert r.status_code == 200, r.text
            flags = FlagsResponse(
                project_id=pid,
                model_version="test",
                rules_version="test",
                promise=PromiseCheck(
                    title="Render test",
                    first_mention_s=None,
                    first_mention_text=None,
                    best_match_s=None,
                    best_similarity=None,
                ),
                flags=[],
                edits=[
                    _edit("e1", "CUT", 2, 6),
                    _edit("m1", "MOVE", 15, 18, target=1, simulatable=False),
                ],
            )
            svc.db.put_artifact(pid, "flags", "test", flags.model_dump_json())
            body = {
                "edit_ids": ["e1", "m1"],
                "custom_edits": [{"action": "SPEED", "start": 8, "end": 12, "factor": 2.0}],
            }
            st = c.post(f"/api/projects/{pid}/render", json=body)
            assert st.status_code == 202, st.text
            rid = st.json()["render_id"]
            # TestClient runs background tasks before returning
            done = c.get(f"/api/projects/{pid}/renders/{rid}").json()
            assert done["status"] == "done", done
            assert done["plan"]["moved_edit_ids"] == ["m1"]

            name = render_service.name_for(rid)
            out = tmp_path / "out.mp4"
            svc.store.decrypt_to(pid, name, out)
            assert b"ftyp" in out.read_bytes()[:64]
            assert b"ftyp" not in svc.store.path(pid, name).read_bytes()[:64]  # encrypted at rest
            info = probe_mod.probe(out)
            assert info.duration_s == pytest.approx(20 - 4 - 2, abs=0.3)  # cut 4 s, 4 s at 2x
            assert info.has_audio and info.height <= load_config("render")["max_height"]

            part = c.get(
                f"/api/projects/{pid}/renders/{rid}/media", headers={"Range": "bytes=0-99"}
            )
            assert part.status_code == 206 and len(part.content) == 100

            again = c.post(f"/api/projects/{pid}/render", json=body).json()  # cached
            assert again["render_id"] == rid and again["status"] == "done"
            assert c.get(f"/api/projects/{pid}/renders/0000000000000000/media").status_code == 404
    finally:
        app.dependency_overrides.clear()
