from fastapi.testclient import TestClient

from backend.app.abtest import ABRequest, compare
from backend.app.deps import build_services, get_services
from backend.app.main import app
from backend.app.schemas.project import Language
from backend.tests.helpers import FIX, HashingEmbedder

SCRIPT = (FIX / "en_script.txt").read_text(encoding="utf-8")
# Version B: same body, a tighter hook (no housekeeping, the promise first)
HOOK_B = (
    "# I Built an AI Agent in 24 Hours\n\nBy the end of this video you will see an AI agent "
    "book a real dinner reservation on its own. I built it in 24 hours, and it actually works.\n\n"
)
BODY = SCRIPT.split("So what is an AI agent?", 1)[1]
SCRIPT_B = HOOK_B + "So what is an AI agent?" + BODY


def _req():
    return ABRequest(
        title="I Built an AI Agent in 24 Hours",
        language=Language.EN,
        script_a=SCRIPT,
        script_b=SCRIPT_B,
        name_a="Original",
        name_b="Tight hook",
    )


def test_compare_shape_and_labels():
    res = compare(_req(), HashingEmbedder())
    assert "Not a real A/B test" in res.label
    keys = [m.key for m in res.metrics]
    assert keys == ["r30", "r60", "title_at", "fillers", "pace", "promise", "flags60"]
    assert res.a.points[0].retention == 1.0 and res.b.points[0].retention == 1.0
    assert res.b.duration_s < res.a.duration_s  # the tight hook is shorter
    fillers = next(m for m in res.metrics if m.key == "fillers")
    assert fillers.winner == "b"  # version A's hook has "Um", "honestly", "So"
    assert res.summary


def test_identical_versions_tie():
    req = _req()
    req.script_b = req.script_a
    res = compare(req, HashingEmbedder())
    assert all(m.winner in ("tie", "n/a") for m in res.metrics)
    assert res.summary.startswith("No clear winner")


def test_ab_endpoint(settings):
    svc = build_services(settings)
    svc._embedder = HashingEmbedder()
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with TestClient(app) as c:
            r = c.post("/api/ab-test", json=_req().model_dump(mode="json"))
            assert r.status_code == 200, r.text
            assert len(r.json()["metrics"]) == 7
            bad = c.post("/api/ab-test", json={**_req().model_dump(mode="json"), "script_b": "x"})
            assert bad.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_ab_compare_two_projects(settings):
    svc = build_services(settings)
    svc._embedder = HashingEmbedder()
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with TestClient(app) as c:
            ids = []
            for text in (SCRIPT, SCRIPT_B):
                pid = c.post(
                    "/api/projects",
                    json={
                        "title": "I Built an AI Agent in 24 Hours",
                        "category": "tech",
                        "language": "en",
                    },
                ).json()["id"]
                c.post(f"/api/projects/{pid}/script", json={"text": text})
                c.post(f"/api/projects/{pid}/analyze")
                ids.append(pid)
            r = c.post("/api/projects/ab-compare", json={"project_a": ids[0], "project_b": ids[1]})
            assert r.status_code == 200, r.text
            d = r.json()
            assert "two analysed projects" in d["label"] and d["b"]["name"].endswith("(B)")
            assert [m["key"] for m in d["metrics"]][:2] == ["r30", "r60"]  # no video signals
            same = c.post(
                "/api/projects/ab-compare", json={"project_a": ids[0], "project_b": ids[0]}
            )
            assert same.status_code == 422
    finally:
        app.dependency_overrides.clear()
