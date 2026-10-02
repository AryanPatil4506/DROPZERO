"""Build real per-second retention curves + captions from MOOCCubeX.

Inputs (data/raw/mooccubex/): user-video.json (watch logs, one viewer per line), video.json
(timestamped captions), video_id-ccid.txt (watch-log video id -> caption id).
Outputs (data/processed/mooc/): curves.jsonl, captions.jsonl, summary.json.

The watch-log file may still be downloading: we read a fixed byte snapshot (recorded in
summary.json) so the run is reproducible, and drop a truncated last line.

    python scripts/build_mooc_curves.py
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import orjson
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.validation.mooc import (  # noqa: E402
    add_coverage,
    anchor_start,
    is_test,
    retention_from_diff,
)

RAW = ROOT / "data" / "raw" / "mooccubex"
OUT = ROOT / "data" / "processed" / "mooc"
FULL_SIZE = 3_179_221_944  # user-video.json Content-Length on lfs.aminer.cn


def iter_viewers(path: Path, limit: int):
    with path.open("rb") as f:
        read = 0
        for line in f:
            read += len(line)
            if read > limit:
                return
            try:
                yield orjson.loads(line)
            except orjson.JSONDecodeError:
                continue  # truncated final line of a partial download


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "mooc.yaml").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    vid2cc = {}
    with (RAW / "video_id-ccid.txt").open(encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                vid2cc[parts[0]] = parts[1]
    cap_meta = {}
    with (RAW / "video.json").open("rb") as f:
        for line in f:
            v = orjson.loads(line)
            if v.get("end"):
                cap_meta[v["ccid"]] = (float(max(v["end"])), len(v["text"]))
    print(f"id map {len(vid2cc):,}, captioned lectures {len(cap_meta):,} ({time.time()-t0:.0f}s)")

    log = RAW / "user-video.json"
    limit = log.stat().st_size
    tol = cfg["start_tolerance_s"]

    # pass 1: count viewers / starters per caption id
    viewers, starters = Counter(), Counter()
    n_users = 0
    for u in iter_viewers(log, limit):
        n_users += 1
        for v in u["seq"]:
            cc = vid2cc.get(v["video_id"])
            if cc is None or cc not in cap_meta or not v["segment"]:
                continue
            viewers[cc] += 1
            if min(s["start_point"] for s in v["segment"]) <= tol:
                starters[cc] += 1
    print(f"pass 1: {n_users:,} viewers in {limit/1e9:.2f} GB snapshot ({time.time()-t0:.0f}s)")

    ok = [
        cc
        for cc, n in starters.items()
        if n >= cfg["min_starters"]
        and cfg["min_duration_s"] <= cap_meta[cc][0] <= cfg["max_duration_s"]
        and cap_meta[cc][1] >= cfg["min_caption_lines"]
    ]
    chosen = sorted(ok, key=lambda c: (-starters[c], c))[: cfg["max_videos"]]
    chosen_set = set(chosen)
    print(f"qualifying lectures {len(ok):,}; using {len(chosen):,}")

    # pass 2: per-second coverage for chosen lectures
    diffs = {cc: np.zeros(int(np.ceil(cap_meta[cc][0])) + 1, dtype=np.int64) for cc in chosen}
    for u in iter_viewers(log, limit):
        for v in u["seq"]:
            cc = vid2cc.get(v["video_id"])
            if cc not in chosen_set or not v["segment"]:
                continue
            segs = v["segment"]
            if min(s["start_point"] for s in segs) > tol:
                continue
            add_coverage(
                diffs[cc], anchor_start([(s["start_point"], s["end_point"]) for s in segs], tol)
            )
    print(f"pass 2 done ({time.time()-t0:.0f}s)")

    n_test = 0
    with (OUT / "curves.jsonl").open("w", encoding="utf-8") as f:
        for cc in chosen:
            r = retention_from_diff(diffs[cc], starters[cc])
            test = is_test(cc, cfg["test_fraction"])
            n_test += test
            f.write(
                json.dumps(
                    {
                        "ccid": cc,
                        "split": "test" if test else "train",
                        "n_starters": starters[cc],
                        "n_viewers": viewers[cc],
                        "duration_s": round(cap_meta[cc][0], 3),
                        "retention": [round(float(x), 4) for x in r],
                    }
                )
                + "\n"
            )
    with (RAW / "video.json").open("rb") as f, (OUT / "captions.jsonl").open("wb") as out:
        for line in f:
            v = orjson.loads(line)
            if v["ccid"] in chosen_set:
                out.write(orjson.dumps({k: v[k] for k in ("ccid", "start", "end", "text")}))
                out.write(b"\n")
    summary = {
        "source": "MOOCCubeX (THU-KEG), user-video.json + video.json + video_id-ccid.txt",
        "what_it_is": "real in-video viewing of Chinese online-course lectures (not YouTube)",
        "retention_definition": "share of viewers who started within start_tolerance_s whose "
        "watched intervals cover second t; skipped parts count as not watched",
        "watch_log_bytes_used": limit,
        "watch_log_complete": limit == FULL_SIZE,
        "viewers_read": n_users,
        "lectures_qualifying": len(ok),
        "lectures_used": len(chosen),
        "train": len(chosen) - n_test,
        "test": n_test,
        "config": cfg,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                k: summary[k]
                for k in ("viewers_read", "lectures_qualifying", "lectures_used", "train", "test")
            }
        ),
        f"total {time.time()-t0:.0f}s",
    )


if __name__ == "__main__":
    main()
