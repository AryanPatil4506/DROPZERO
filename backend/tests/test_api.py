import hashlib
import os
import subprocess
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.deps import build_services, get_services
from backend.app.ingestion import probe as probe_mod
from backend.app.main import app
from backend.app.pipeline import runner
from backend.app.schemas.project import MediaInfo
from backend.tests.helpers import FIX, FakeVisualEncoder, FixtureAsr, HashingEmbedder

MP4_HEAD = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"


@pytest.fixture
def svc(settings):
    s = build_services(settings)
    s._embedder = HashingEmbedder()
    s._vision = FakeVisualEncoder()
    s._asr = FixtureAsr("en")
    return s


@pytest.fixture
def client(svc):
    app.dependency_overrides[get_services] = lambda: svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create(client, lang="en"):
    r = client.post(
        "/api/projects",
        json={"title": "I Built an AI Agent in 24 Hours", "category": "tech", "language": lang},
    )
    assert r.status_code == 201
    return r.json()["id"]


def _work_dirs(svc):
    return [p for p in svc.settings.work_dir.glob("*")] if svc.settings.work_dir.exists() else []


@pytest.mark.parametrize("lang", ["en", "hi", "hinglish"])
def test_script_flow(client, svc, lang):
    pid = _create(client, lang)
    path = FIX / f"{lang}_script.txt"
    with path.open("rb") as f:
        r = client.post(f"/api/projects/{pid}/script", files={"file": (path.name, f)})
    assert r.status_code == 200 and r.json()["source_type"] == "script"
    assert client.get(f"/api/projects/{pid}/features/av").status_code == 404
    job = client.post(f"/api/projects/{pid}/analyze").json()
    job = client.get(f"/api/jobs/{job['id']}").json()  # TestClient runs background tasks inline
    assert job["status"] == "done" and job["progress"] == 1.0, job
    assert job["stages"] == runner.SCRIPT_STAGES
    t = client.get(f"/api/projects/{pid}/transcript").json()
    assert t["timing_source"] == "estimated"
    segs = client.get(f"/api/projects/{pid}/segments").json()
    assert all(s["timing_source"] == "estimated" for s in segs)
    fs = client.get(f"/api/projects/{pid}/features/text").json()
    assert len(fs["segments"]) == len(segs) and fs["timing_source"] == "estimated"
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "ready" and p["duration_s"] == segs[-1]["end"]
    pred = client.get(f"/api/projects/{pid}/prediction").json()
    assert pred["points"][0] == {"t": 0.0, "retention": 1.0, "lower": 1.0, "upper": 1.0}
    assert len(pred["segments"]) == len(segs)
    fl = client.get(f"/api/projects/{pid}/flags").json()
    assert fl["promise"]["title"] and fl["model_version"] == pred["model_version"]
    sim_ids = [e["id"] for e in fl["edits"] if e["simulatable"]]
    if sim_ids:
        sim = client.post(f"/api/projects/{pid}/simulate", json={"edit_ids": sim_ids}).json()
        assert "Simulated" in sim["label"] and sim["original"] == pred["points"]
    assert (
        client.post(f"/api/projects/{pid}/simulate", json={"edit_ids": ["nope"]}).status_code == 422
    )
    # script text is stored encrypted only
    enc = svc.store.path(pid, "script").read_bytes()
    assert path.read_bytes()[:30] not in enc
    assert _work_dirs(svc) == []


def test_script_json_body(client):
    pid = _create(client)
    r = client.post(f"/api/projects/{pid}/script", json={"text": "Hello there. " * 40})
    assert r.status_code == 200


def _fake_video(tmp_path):
    src = tmp_path / "creator_original.mp4"
    src.write_bytes(MP4_HEAD + os.urandom(200_000))
    return src


def _silent_wav(_src, dest):
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)


def _static_frames(_src, cfg):
    return np.zeros((600, cfg["height"], cfg["width"]), dtype=np.uint8)  # 300 s at 2 fps


def test_video_flow_mocked_media(client, svc, tmp_path, monkeypatch):
    info = MediaInfo(duration_s=215.0, has_audio=True, has_video=True, fps=30)
    monkeypatch.setattr("backend.app.api.projects.probe", lambda p: info)
    monkeypatch.setattr(runner, "extract_audio", _silent_wav)
    monkeypatch.setattr(runner, "sample_frames", _static_frames)
    src = _fake_video(tmp_path)
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    pid = _create(client)
    with src.open("rb") as f:
        r = client.post(f"/api/projects/{pid}/video", files={"file": (src.name, f)})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["source_sha256"] == sha_before == hashlib.sha256(src.read_bytes()).hexdigest()
    assert p["warnings"]  # 3.6 min is outside the tested 5–15 min range
    assert src.read_bytes()[:64] not in svc.store.path(pid, "original").read_bytes()

    job = client.post(f"/api/projects/{pid}/analyze").json()
    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "done", job
    t = client.get(f"/api/projects/{pid}/transcript").json()
    assert t["timing_source"] == "asr" and t["asr_model"] == "fixture/asr"
    segs = client.get(f"/api/projects/{pid}/segments").json()
    assert segs[0]["kind"] == "silence"  # the fixture's 18 s music intro
    av = client.get(f"/api/projects/{pid}/features/av").json()
    assert av["has_video"] and av["scene_cuts"] == [] and len(av["segments"]) == len(segs)
    assert all(s["static_ratio"] == 1.0 for s in av["segments"])  # all-black mocked frames
    assert _work_dirs(svc) == []

    # re-analysis hits the encrypted ASR cache
    client.post(f"/api/projects/{pid}/analyze")
    assert svc._asr.calls == 1

    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert not svc.store.path(pid, "original").exists()
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_failed_job_cleans_up(client, svc, tmp_path, monkeypatch):
    info = MediaInfo(duration_s=400.0, has_audio=True, has_video=True)
    monkeypatch.setattr("backend.app.api.projects.probe", lambda p: info)
    monkeypatch.setattr(runner, "extract_audio", _silent_wav)

    def boom(*a, **k):
        raise RuntimeError("GPU fell over")

    svc._asr.transcribe = boom
    monkeypatch.setattr(runner, "sample_frames", _static_frames)
    pid = _create(client)
    with _fake_video(tmp_path).open("rb") as f:
        client.post(f"/api/projects/{pid}/video", files={"file": ("v.mp4", f)})
    job = client.post(f"/api/projects/{pid}/analyze").json()
    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "failed" and "GPU fell over" in job["error"]
    assert job["stage"] == "transcribe"
    assert client.get(f"/api/projects/{pid}").json()["status"] == "failed"
    assert _work_dirs(svc) == []


@pytest.mark.parametrize(
    "name,content,code",
    [("notes.mp4", b"hello I am text, not video", 422), ("v.avi", MP4_HEAD + b"x" * 100, 422)],
)
def test_upload_rejections(client, name, content, code):
    pid = _create(client)
    r = client.post(f"/api/projects/{pid}/video", files={"file": (name, content)})
    assert r.status_code == code


def test_duration_rejection(client, monkeypatch):
    info = MediaInfo(duration_s=30.0, has_audio=True, has_video=True)
    monkeypatch.setattr("backend.app.api.projects.probe", lambda p: info)
    pid = _create(client)
    r = client.post(f"/api/projects/{pid}/video", files={"file": ("v.mp4", MP4_HEAD * 10)})
    assert r.status_code == 422 and "too short" in r.json()["detail"]


def test_validation_endpoint(client):
    v = client.get("/api/validation").json()
    assert v["n_videos_test"] > 0 and "not YouTube" in v["dataset"]
    assert {"mae", "rmse", "pearson", "spearman"} <= set(v["metrics"]) <= set(v["baseline"])
    llm = v["llm_baseline"]  # plain-LLM baseline served next to the model's numbers
    assert {"dropzero", "llm", "baseline"} <= set(llm["methods"]) and llm["lectures"] > 0


def test_analyze_requires_source(client):
    pid = _create(client)
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 409


def test_no_media_key_is_explicit(tmp_path):
    from backend.app.settings import Settings

    s = build_services(Settings(data_dir=tmp_path / "v", media_key="", _env_file=None))
    app.dependency_overrides[get_services] = lambda: s
    try:
        with TestClient(app) as c:
            pid = c.post(
                "/api/projects", json={"title": "x", "category": "vlog", "language": "hi"}
            ).json()["id"]
            r = c.post(f"/api/projects/{pid}/script", json={"text": "नमस्ते।"})
            assert r.status_code == 503 and "MEDIA_KEY" in r.json()["detail"]
            assert c.get("/api/health").json()["media_key_configured"] is False
    finally:
        app.dependency_overrides.clear()


def _ffmpeg():
    try:
        return probe_mod.find_tool("ffmpeg")
    except probe_mod.ToolMissing:
        return None


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg not installed")
def test_real_ffmpeg_probe_and_audio(client, svc, tmp_path):
    """Real ffprobe + ffmpeg on a generated 61 s clip: black for 30 s, then white, with a tone.
    ASR is the fixture; frames, scene cuts and audio energy are real."""
    src = tmp_path / "tone.mp4"
    graph = (
        "color=c=black:s=64x64:r=5:d=30[a];color=c=white:s=64x64:r=5:d=31[b];"
        "[a][b]concat=n=2:v=1:a=0"
    )
    subprocess.run(
        [
            _ffmpeg(),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            graph,
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=61",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(src),
        ],
        check=True,
        timeout=120,
    )
    pid = _create(client)
    with src.open("rb") as f:
        r = client.post(f"/api/projects/{pid}/video", files={"file": (src.name, f)})
    assert r.status_code == 200, r.text
    media = r.json()["media"]
    assert media["has_audio"] and abs(media["duration_s"] - 61) < 0.5 and media["fps"] == 5
    job = client.post(f"/api/projects/{pid}/analyze").json()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
    av = client.get(f"/api/projects/{pid}/features/av").json()
    assert len(av["scene_cuts"]) == 1 and abs(av["scene_cuts"][0] - 30.0) <= 0.5
    assert _work_dirs(svc) == []


def test_music_and_other_categories(client):
    for cat in ("music", "other"):
        r = client.post("/api/projects", json={"title": "x", "category": cat, "language": "en"})
        assert r.status_code == 201 and r.json()["category"] == cat
    bad = client.post("/api/projects", json={"title": "x", "category": "sports", "language": "en"})
    assert bad.status_code == 422
