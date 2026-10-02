"""GET /api/projects/{id}/media: decrypted streaming with HTTP Range for the dashboard player."""

import os

import pytest

from backend.app.schemas.project import MediaInfo
from backend.tests.test_api import MP4_HEAD, _create, client, svc  # noqa: F401  (fixtures)


@pytest.fixture
def video(client, svc, tmp_path, monkeypatch):  # noqa: F811
    info = MediaInfo(duration_s=400.0, has_audio=True, has_video=True, fps=30)
    monkeypatch.setattr("backend.app.api.projects.probe", lambda p: info)
    data = MP4_HEAD + os.urandom(3 * (1 << 20) + 12345)  # spans several 1 MiB chunks
    pid = _create(client)
    r = client.post(f"/api/projects/{pid}/video", files={"file": ("clip.mp4", data)})
    assert r.status_code == 200, r.text
    return pid, data


def test_full_file(client, video):  # noqa: F811
    pid, data = video
    r = client.get(f"/api/projects/{pid}/media")
    assert r.status_code == 200
    assert r.content == data
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "header,start,end",
    [
        ("bytes=0-99", 0, 99),
        ("bytes=1048570-1048590", 1048570, 1048590),  # crosses a chunk boundary
        ("bytes=2000000-", 2000000, None),
        ("bytes=-500", None, None),
    ],
)
def test_ranges(client, video, header, start, end):  # noqa: F811
    pid, data = video
    size = len(data)
    if start is None:
        start, end = size - 500, size - 1
    if end is None:
        end = size - 1
    r = client.get(f"/api/projects/{pid}/media", headers={"Range": header})
    assert r.status_code == 206
    assert r.content == data[start : end + 1]
    assert r.headers["content-range"] == f"bytes {start}-{end}/{size}"
    assert int(r.headers["content-length"]) == end - start + 1


def test_unsatisfiable_range(client, video):  # noqa: F811
    pid, data = video
    r = client.get(f"/api/projects/{pid}/media", headers={"Range": f"bytes={len(data)}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(data)}"


def test_script_project_has_no_media(client):  # noqa: F811
    pid = _create(client)
    client.post(f"/api/projects/{pid}/script", json={"text": "Hello there. " * 50})
    assert client.get(f"/api/projects/{pid}/media").status_code == 404
    assert client.get("/api/projects/nope/media").status_code == 404
