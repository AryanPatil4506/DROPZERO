"""Render a RenderPlan with ffmpeg in one pass: trim each piece, speed it up if needed, fade the
audio at every join (no clicks), concatenate, cap the height. NVENC first, CPU fallback.

Only a decrypted working copy of the original is read; the creator's file is never modified.
"""

import subprocess
from pathlib import Path

from backend.app.ingestion.probe import find_tool
from backend.app.render.plan import Piece


def _atempo(factor: float) -> str:
    """atempo accepts 0.5-2.0 per stage; chain stages for larger factors."""
    stages: list[str] = []
    f = factor
    while f > 2.0 + 1e-9:
        stages.append("atempo=2.0")
        f /= 2.0
    if abs(f - 1.0) > 1e-6:
        stages.append(f"atempo={f:.6f}")
    return ",".join(stages)


def build_filter(pieces: list[Piece], has_audio: bool, max_height: int, fade_ms: int) -> str:
    parts: list[str] = []
    labels: list[str] = []
    fade = fade_ms / 1000
    for i, p in enumerate(pieces):
        speed = f"/{p.factor:.6f}" if p.factor != 1.0 else ""
        parts.append(
            f"[0:v]trim=start={p.start:.3f}:end={p.end:.3f},setpts=(PTS-STARTPTS){speed}[v{i}]"
        )
        labels.append(f"[v{i}]")
        if has_audio:
            out_len = p.out_duration
            chain = [f"atrim=start={p.start:.3f}:end={p.end:.3f}", "asetpts=PTS-STARTPTS"]
            if tempo := _atempo(p.factor):
                chain.append(tempo)
            if out_len > 4 * fade:
                chain += [
                    f"afade=t=in:d={fade:.3f}",
                    f"afade=t=out:st={out_len - fade:.3f}:d={fade:.3f}",
                ]
            parts.append(f"[0:a]{','.join(chain)}[a{i}]")
            labels.append(f"[a{i}]")
    n = len(pieces)
    outs = "[vc][ac]" if has_audio else "[vc]"
    parts.append(f"{''.join(labels)}concat=n={n}:v=1:a={1 if has_audio else 0}{outs}")
    # downscale only, keep even dimensions for H.264
    parts.append(f"[vc]scale=-2:'min({max_height},ih)':flags=bicubic,format=yuv420p[vout]")
    return ";".join(parts)


def render(src: Path, dest: Path, pieces: list[Piece], has_audio: bool, cfg: dict) -> str:
    """Encode `dest` and return the encoder used. On failure, raise with ffmpeg's tail."""
    if not pieces:
        raise RuntimeError("the edit plan removes the whole video")
    graph = build_filter(pieces, has_audio, cfg["max_height"], cfg["audio_fade_ms"])
    script = dest.with_suffix(".filter.txt")  # long graphs exceed Windows' command-line limit
    script.write_text(graph, encoding="utf-8")
    errors = []
    try:
        for enc in cfg["encoders"]:
            cmd = [
                find_tool("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(src),
                "-/filter_complex", str(script),
                "-map", "[vout]",
                *(["-map", "[ac]", *cfg["audio_args"]] if has_audio else []),
                "-c:v", enc["name"], *enc["args"],
                "-movflags", "+faststart",
                str(dest),
            ]  # fmt: skip
            out = subprocess.run(cmd, capture_output=True, check=False, timeout=cfg["timeout_s"])
            if out.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
                return enc["name"]
            errors.append(f"{enc['name']}: {out.stderr.decode(errors='replace')[-400:]}")
            dest.unlink(missing_ok=True)
    finally:
        script.unlink(missing_ok=True)
    raise RuntimeError("ffmpeg render failed. " + " | ".join(errors))
