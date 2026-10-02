import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from backend.app.schemas.project import MediaInfo
from backend.app.settings import get_settings


class ToolMissing(RuntimeError):
    pass


@lru_cache
def find_tool(name: str) -> str:
    """ffmpeg/ffprobe: explicit setting, then PATH, then the winget install dir (winget does not
    update PATH for already-running shells)."""
    explicit = getattr(get_settings(), name)
    if explicit:
        return explicit
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        for exe in sorted(base.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe")):
            return str(exe)
    raise ToolMissing(f"{name} not found; install ffmpeg or set DROPZERO_{name.upper()}")


def _fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    num, _, den = rate.partition("/")
    try:
        return round(float(num) / float(den or 1), 3)
    except (ValueError, ZeroDivisionError):
        return None


def parse_ffprobe(data: dict) -> MediaInfo:
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or (v or a or {}).get("duration") or 0.0)
    return MediaInfo(
        duration_s=round(duration, 3),
        has_audio=a is not None,
        has_video=v is not None,
        fps=_fps(v.get("avg_frame_rate")) if v else None,
        width=v.get("width") if v else None,
        height=v.get("height") if v else None,
        audio_sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        audio_channels=a.get("channels") if a else None,
        container=fmt.get("format_name"),
    )


def probe(path: Path) -> MediaInfo:
    out = subprocess.run(
        [
            find_tool("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if out.returncode != 0:
        raise ValueError("ffprobe could not read the file; it may be corrupt")
    return parse_ffprobe(json.loads(out.stdout))
