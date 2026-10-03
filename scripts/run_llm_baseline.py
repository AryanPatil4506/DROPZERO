"""Compare DROPZERO vs a plain local LLM vs the category-average baseline on held-out lectures.

    python scripts/run_llm_baseline.py [--n 40] [--k 5]

Writes models/llm_baseline.json and adds an "llm_baseline" section to models/validation.json.
"""

import argparse
import json
import pickle  # our own local feature cache (data/processed), never untrusted files
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import load_config  # noqa: E402
from backend.app.explain.llm import LocalLLM  # noqa: E402
from backend.app.model.predict import drop_probs, load_model  # noqa: E402
from backend.app.validation.llm_baseline import (  # noqa: E402
    PROMPT,
    parse_seconds,
    score_points,
    top_k_points,
    transcript_text,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--max-chars", type=int, default=6000)
    args = ap.parse_args()
    mcfg = load_config("model")
    major, tol = mcfg["detection"]["major_drop_hazard"], mcfg["detection"]["tolerance_s"]
    data = ROOT / "data" / "processed" / "mooc"
    with (data / "dataset.pkl").open("rb") as f:
        lectures = [x for x in pickle.load(f)["lectures"] if x["split"] == "test"]
    caps = {}
    with (data / "captions.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            caps[r["ccid"]] = r
    # deterministic subset: held-out lectures with at least one real major drop, by id
    lectures = sorted(
        [x for x in lectures if any(h >= major for h in x["hazard"][1:]) and x["ccid"] in caps],
        key=lambda x: x["ccid"],
    )[: args.n]
    art = load_model()
    llm = LocalLLM(load_config("llm"))
    totals = {m: [0, 0, 0, 0] for m in ("dropzero", "llm", "baseline")}  # hits, found, actual, pts
    t0 = time.time()
    for n, lec in enumerate(lectures, 1):
        k = args.k
        ours = top_k_points(drop_probs(art["clf"], lec["X"]), lec, k)
        base = top_k_points(art["baseline"].predict(lec["X"]), lec, k)
        prompt = PROMPT.format(
            dur=int(lec["duration_s"]),
            k=k,
            skip=int(lec["ends"][0]),
            transcript=transcript_text(caps[lec["ccid"]], args.max_chars),
        )
        llm_pts = parse_seconds(llm.chat("Reply with JSON only.", prompt), k, lec["duration_s"])
        for name, pts in (("dropzero", ours), ("llm", llm_pts), ("baseline", base)):
            h, fnd, act = score_points(pts, lec, major, tol)
            tot = totals[name]
            tot[0] += h
            tot[1] += fnd
            tot[2] += act
            tot[3] += len(pts)
        print(
            f"{n}/{len(lectures)} ({time.time() - t0:.0f}s) llm gave {len(llm_pts)} points",
            flush=True,
        )

    result = {
        "what": "Top-k drop points per lecture, scored against real major drops "
        f"(segment losing >= {major:.0%} of its viewers, +-{tol:.0f} s, first segment excluded)",
        "lectures": len(lectures),
        "k": args.k,
        "llm_model": llm.name,
        "note": "The plain LLM sees only the timestamped transcript. It is the same small local "
        "open-source model the app uses, not a frontier chatbot; a larger LLM may do better.",
        "methods": {},
    }
    for name, (h, fnd, act, pts) in totals.items():
        result["methods"][name] = {
            "precision": round(h / pts, 3) if pts else 0.0,
            "recall": round(fnd / act, 3) if act else 0.0,
            "drops_found": fnd,
            "drops_total": act,
            "points_named": pts,
        }
    (ROOT / "models" / "llm_baseline.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8"
    )
    vpath = ROOT / "models" / "validation.json"
    v = json.loads(vpath.read_text(encoding="utf-8"))
    v["llm_baseline"] = result
    vpath.write_text(json.dumps(v, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    _ = np  # numpy imported for pickle'd arrays
    main()
