"""Type checks by content, not just extension."""

from pathlib import Path

from backend.app.config import load_config

# ISO-BMFF (MP4/MOV with ftyp) or classic QuickTime top-level atoms.
_MOV_ATOMS = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"}


class ValidationError(ValueError):
    pass


def check_video_header(head: bytes, filename: str) -> None:
    cfg = load_config("ingestion")
    ext = Path(filename).suffix.lower()
    if ext not in cfg["video_extensions"]:
        raise ValidationError(f"unsupported video type {ext!r}; use MP4 or MOV")
    if len(head) < 12 or head[4:8] not in _MOV_ATOMS:
        raise ValidationError("file content is not an MP4/MOV container")


def decode_script(data: bytes, filename: str) -> str:
    cfg = load_config("ingestion")
    ext = Path(filename).suffix.lower()
    if ext not in cfg["script_extensions"]:
        raise ValidationError(f"unsupported script type {ext!r}; use TXT or MD")
    if len(data) > cfg["max_script_bytes"]:
        raise ValidationError("script too large")
    if b"\x00" in data:
        raise ValidationError("script is not a text file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValidationError("script must be UTF-8 text") from e
    if not text.strip():
        raise ValidationError("script is empty")
    return text


def duration_warnings(duration_s: float) -> list[str]:
    """Raises if outside hard limits; returns warnings if outside the tested range."""
    cfg = load_config("ingestion")
    if duration_s < cfg["min_duration_s"]:
        raise ValidationError(f"too short: {duration_s:.0f}s (minimum {cfg['min_duration_s']}s)")
    if duration_s > cfg["max_duration_s"]:
        raise ValidationError(f"too long: {duration_s:.0f}s (maximum {cfg['max_duration_s']}s)")
    lo, hi = cfg["recommended_min_s"], cfg["recommended_max_s"]
    if not lo <= duration_s <= hi:
        return [
            f"Duration {duration_s / 60:.1f} min is outside the tested 5–15 min range; "
            "results may be less reliable."
        ]
    return []
