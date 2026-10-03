"""Build the demo "golden project" video: the English fixture script, voiced with Windows'
built-in text-to-speech (offline, synthetic speech), with a 12 s silent opening and a colour
change per paragraph. It is a DEMO ASSET, not data: it exists so one project shows every
feature (slow hook, late title, intro promise kept late, repetition, rewrite, render, A/B).

    python scripts/make_demo_video.py

Writes (gitignored, under data/private):
    videos/demo_ai_agent.mp4 + demo_ai_agent.title.txt
    demo/ab_original.txt, demo/ab_promise_first.txt  (the A/B pair for the hook demo)
"""

import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ingestion.probe import find_tool  # noqa: E402
from backend.app.transcription.script_timing import parse_script  # noqa: E402

FIX = ROOT / "backend" / "tests" / "fixtures"
OUT_VIDEOS = ROOT / "data" / "private" / "videos"
OUT_DEMO = ROOT / "data" / "private" / "demo"
TITLE = "I Built an AI Agent in 24 Hours"
VOICE = "Microsoft Zira Desktop"
LEAD_SILENCE_S = 12.0
GAP_S = 0.7
RATE = 22050
COLOURS = ["0x1B2433", "0x2B1F33", "0x16302B", "0x33261B", "0x1F2B3D", "0x2E1B24"]

PS = r"""
Add-Type -AssemblyName System.Speech
$items = Get-Content -Raw -Encoding UTF8 '{list}' | ConvertFrom-Json
$bits = [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen
$ch = [System.Speech.AudioFormat.AudioChannel]::Mono
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({rate}, $bits, $ch)
foreach ($it in $items) {{
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice('{voice}')
  $s.Rate = 1
  $s.SetOutputToWaveFile($it.path, $fmt)
  $s.Speak($it.text)
  $s.Dispose()
}}
"""


def main() -> None:
    paragraphs = parse_script((FIX / "en_script.txt").read_text(encoding="utf-8"))
    texts = [" ".join(p) for p in paragraphs]
    work = Path(tempfile.mkdtemp())
    try:
        items = [{"path": str(work / f"p{i:02d}.wav"), "text": t} for i, t in enumerate(texts)]
        (work / "list.json").write_text(json.dumps(items), encoding="utf-8")
        ps = PS.format(list=work / "list.json", rate=RATE, voice=VOICE)
        (work / "tts.ps1").write_text(ps, encoding="utf-8")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(work / "tts.ps1"),
            ],
            check=True,
            timeout=600,
        )

        # audio: silent lead-in, then each paragraph with a short gap
        frames, blocks = [], []  # blocks = (duration_s) per colour segment
        silence = lambda s: b"\x00\x00" * int(s * RATE)  # noqa: E731
        frames.append(silence(LEAD_SILENCE_S))
        blocks.append(LEAD_SILENCE_S)
        for it in items:
            with wave.open(it["path"], "rb") as w:
                data = w.readframes(w.getnframes())
            frames.append(data + silence(GAP_S))
            blocks.append(len(data) / 2 / RATE + GAP_S)
        wav = work / "audio.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(frames))

        # video: one colour block per paragraph (scene cut at each paragraph), black lead-in
        n = len(blocks)
        srcs = [f"color=c=black:s=1280x720:r=25:d={blocks[0]:.3f}[v0]"] + [
            f"color=c={COLOURS[i % len(COLOURS)]}:s=1280x720:r=25:d={d:.3f}[v{i}]"
            for i, d in enumerate(blocks)
            if i
        ]
        graph = (
            ";".join(srcs)
            + ";"
            + "".join(f"[v{i}]" for i in range(n))
            + f"concat=n={n}:v=1:a=0,format=yuv420p[vout]"
        )
        OUT_VIDEOS.mkdir(parents=True, exist_ok=True)
        out = OUT_VIDEOS / "demo_ai_agent.mp4"
        subprocess.run(
            [
                find_tool("ffmpeg"),
                "-v",
                "error",
                "-y",
                "-filter_complex",
                graph,
                "-i",
                str(wav),
                "-map",
                "[vout]",
                "-map",
                "0:a",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                str(out),
            ],
            check=True,
            timeout=600,
        )
        (OUT_VIDEOS / "demo_ai_agent.title.txt").write_text(TITLE, encoding="utf-8")
        print("wrote", out.relative_to(ROOT), f"{sum(blocks):.1f}s")

        # A/B pair for the hook demo (same body, two openings)
        from backend.tests.test_abtest import SCRIPT, SCRIPT_B

        OUT_DEMO.mkdir(parents=True, exist_ok=True)
        (OUT_DEMO / "ab_original.txt").write_text(SCRIPT, encoding="utf-8")
        (OUT_DEMO / "ab_promise_first.txt").write_text(SCRIPT_B, encoding="utf-8")
        print(
            "wrote",
            (OUT_DEMO / "ab_original.txt").relative_to(ROOT),
            (OUT_DEMO / "ab_promise_first.txt").relative_to(ROOT),
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
