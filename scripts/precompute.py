"""Run the full DROPZERO pipeline on every video in a folder and write results + a summary.

    python scripts/precompute.py [--videos data/private/videos] [--out data/private/results]

Uses the real app (encrypted storage, GPU Whisper, LaBSE, retention model, detector, simulation).
Language is detected from the first 30 s; titles come from file names unless a
<video>.title.txt file sits next to the video. Outputs stay in data/private (gitignored).
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.deps import get_services  # noqa: E402
from backend.app.detection.flags import mmss  # noqa: E402
from backend.app.ingestion.audio import extract_audio, load_wav  # noqa: E402
from backend.app.main import app  # noqa: E402

CATEGORY_HINTS = {"edu": "education", "system": "education", "vlog": "vlog", "tech": "tech"}


def guess(path: Path) -> tuple[str, str]:
    t = path.with_suffix(".title.txt")
    title = t.read_text(encoding="utf-8").strip() if t.exists() else path.stem.replace("_", " ")
    cat = next((c for k, c in CATEGORY_HINTS.items() if k in path.stem.lower()), "education")
    return title, cat


def detect_lang(svc, video: Path) -> tuple[str, float]:
    work = svc.settings.work_dir / f"langid-{video.stem[:20]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        wav = work / "a.wav"
        extract_audio(video, wav)
        return svc.asr.detect_language(load_wav(wav))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_one(c: TestClient, svc, video: Path, out: Path) -> dict:
    t0 = time.time()
    title, cat = guess(video)
    code, prob = detect_lang(svc, video)
    lang = "hi" if code == "hi" else "en"
    pid = c.post("/api/projects", json={"title": title, "category": cat, "language": lang}).json()[
        "id"
    ]
    with video.open("rb") as f:
        r = c.post(f"/api/projects/{pid}/video", files={"file": (video.name, f)})
    r.raise_for_status()
    job = c.post(f"/api/projects/{pid}/analyze").json()
    job = c.get(f"/api/jobs/{job['id']}").json()
    row = {
        "video": video.name,
        "title": title,
        "category": cat,
        "detected_language": code,
        "language_prob": round(prob, 3),
        "declared_language": lang,
        "project_id": pid,
        "job": job["status"],
        "error": job["error"],
    }
    if job["status"] == "done":
        d = out / video.stem[:60]
        d.mkdir(parents=True, exist_ok=True)
        res = {}
        for name, url in [
            ("project", ""),
            ("transcript", "/transcript"),
            ("segments", "/segments"),
            ("features_text", "/features/text"),
            ("features_av", "/features/av"),
            ("prediction", "/prediction"),
            ("flags", "/flags"),
        ]:
            res[name] = c.get(f"/api/projects/{pid}{url}").json()
        # simulate the top edits (high severity first), as a creator would pick them
        rank = {f["id"]: (f["severity"] != "high", -f["risk_score"]) for f in res["flags"]["flags"]}
        sim_edits = [e for e in res["flags"]["edits"] if e["simulatable"]]
        ids = [e["id"] for e in sorted(sim_edits, key=lambda e: rank[e["flag_id"]])][:3]
        if ids:
            res["simulate"] = c.post(f"/api/projects/{pid}/simulate", json={"edit_ids": ids}).json()
        for k, v in res.items():
            (d / f"{k}.json").write_text(
                json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        row["results"] = res
    row["seconds"] = round(time.time() - t0, 1)
    return row


def write_summary(rows: list[dict], path: Path) -> None:
    lines = [
        "# DROPZERO results on team videos",
        "",
        "Predicted curves are model-estimated (model trained on real lecture-viewing data, not "
        "YouTube). Simulations are model-estimated. Rule-based flags are not validated against "
        "retention data.",
        "",
    ]
    for r in rows:
        lines += [f"## {r['title']}", ""]
        if "results" not in r:
            lines += [f"Job {r['job']}: {r['error']}", ""]
            continue
        res = r["results"]
        p, t, pred, fl = res["project"], res["transcript"], res["prediction"], res["flags"]
        end = pred["points"][-1]
        pr = fl["promise"]
        hi = [s for s in pred["segments"] if s["risk"] == "high"]
        first = pr["first_mention_s"]
        lines += [
            f"- File `{r['video']}` · {p['duration_s'] / 60:.1f} min · category {r['category']}"
            f" · processed in {r['seconds']} s",
            f"- Language detected: **{r['detected_language']}** (p={r['language_prob']}); "
            f"ASR mean word confidence {t['mean_confidence']}; {len(t['words'])} words, "
            f"{len(res['segments'])} segments, {len(res['features_av']['scene_cuts'])} scene cuts",
            f"- Warnings: {'; '.join(p['warnings']) or 'none'}",
            f"- Model-estimated retention at the end: {end['retention']:.0%} "
            f"(range {end['lower']:.0%}–{end['upper']:.0%}). Absolute level is NOT "
            "calibrated to YouTube (model learned lecture viewing); use shape and risk.",
            (
                f"- Title promise first addressed: "
                f"{mmss(first) if first is not None else 'never'} (title: \"{pr['title']}\")"
                if len(pr["title"].split()) >= 3
                else f"- Title check skipped: \"{pr['title']}\" is a file name, not a real "
                "title (add <video>.title.txt)"
            ),
            f"- High-risk segments (model): {', '.join(mmss(s['start']) for s in hi) or 'none'}",
            "",
            "| Time | Severity | Flag | Source | Suggested edit |",
            "|---|---|---|---|---|",
        ]
        edits = {e["id"]: e for e in fl["edits"]}
        for f in fl["flags"]:
            ed = "; ".join(edits[i]["reason"] for i in f["edit_ids"]) or "review"
            lines.append(
                f"| {mmss(f['start'])}–{mmss(f['end'])} | {f['severity']} | {f['title']} | "
                f"{f['source']} | {ed} |"
            )
        if "simulate" in res:
            s = res["simulate"]
            lines += [
                "",
                f"Simulated (model-estimated) effect of applying "
                f"{', '.join(s['applied_edit_ids'])}: {s['original_duration_s']:.0f} s → "
                f"{s['simulated_duration_s']:.0f} s, end retention "
                f"{s['delta']['end_retention_pp']:+.1f} pp, average "
                f"{s['delta']['avg_retention_pp']:+.1f} pp.",
            ]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", default=str(ROOT / "data" / "private" / "videos"))
    ap.add_argument("--out", default=str(ROOT / "data" / "private" / "results"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    svc = get_services()
    rows = []
    with TestClient(app) as c:
        for video in sorted(Path(args.videos).iterdir()):
            if video.suffix.lower() not in (".mp4", ".mov"):
                continue
            row = run_one(c, svc, video, out)
            rows.append(row)
            print(
                f"{video.name}: {row['job']} in {row['seconds']}s "
                f"(lang {row['detected_language']} p={row['language_prob']:.2f})"
                + (f" ERROR {row['error']}" if row["error"] else ""),
                flush=True,
            )
    write_summary(rows, out / "SUMMARY.md")
    (out / "summary.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "results"} for r in rows], indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
