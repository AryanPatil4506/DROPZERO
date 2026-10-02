"""Write real API responses for the frontend to develop against: frontend/mock/<lang>/*.json.

Runs the actual pipeline in-process (script mode, real embedding model) on the fixture scripts.
Only the *existing* endpoints are exported here; mocks for not-yet-built endpoints are hand-written
in frontend/mock/contract/ and follow docs/frontend-brief.md.

    python scripts/export_api_samples.py
"""

import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.deps import build_services, get_services  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.settings import Settings  # noqa: E402

FIX = ROOT / "backend" / "tests" / "fixtures"
OUT = ROOT / "frontend" / "mock"
TITLES = {
    "en": ("I Built an AI Agent in 24 Hours", "tech"),
    "hi": ("घर पर गाढ़ा दही कैसे जमाएं", "education"),
    "hinglish": ("15000 ke under best camera phone?", "tech"),
}


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    settings = Settings(
        data_dir=tmp, media_key=base64.b64encode(os.urandom(32)).decode(), _env_file=None
    )
    svc = build_services(settings)
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with TestClient(app) as c:
            for lang, (title, cat) in TITLES.items():
                d = OUT / lang
                d.mkdir(parents=True, exist_ok=True)
                p = c.post(
                    "/api/projects", json={"title": title, "category": cat, "language": lang}
                ).json()
                pid = p["id"]
                text = (FIX / f"{lang}_script.txt").read_text(encoding="utf-8")
                c.post(f"/api/projects/{pid}/script", json={"text": text})
                job = c.post(f"/api/projects/{pid}/analyze").json()
                files = {
                    "job.json": f"/api/jobs/{job['id']}",
                    "project.json": f"/api/projects/{pid}",
                    "transcript.json": f"/api/projects/{pid}/transcript",
                    "segments.json": f"/api/projects/{pid}/segments",
                    "features_text.json": f"/api/projects/{pid}/features/text",
                }
                for name, url in files.items():
                    r = c.get(url)
                    r.raise_for_status()
                    (d / name).write_text(
                        json.dumps(r.json(), ensure_ascii=False, indent=1), encoding="utf-8"
                    )
                print("wrote", d.relative_to(ROOT))
    finally:
        app.dependency_overrides.clear()
        svc.db.engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
