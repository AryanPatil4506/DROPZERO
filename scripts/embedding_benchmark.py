"""Pick the Phase 3 embedding model: which open, locally-run multilingual model best separates a
*repeated point* from *same-topic progress* in English, Hindi and Hinglish?

Selection rule (fixed before running): highest overall ROC-AUC for repeat-vs-progress; if two
models are within 0.01, prefer the smaller one (the demo laptop has 8 GB VRAM shared with Whisper).
The provisional repetition threshold is the cosine cut with the best F1 for
repeat vs (progress + unrelated).

    python scripts/embedding_benchmark.py                 # all candidates
    python scripts/embedding_benchmark.py --models intfloat/multilingual-e5-base

Writes docs/embedding_benchmark.md and docs/embedding_benchmark.json.
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "scripts" / "bench" / "embedding_pairs.yaml"

# All open licences, all run locally.
CANDIDATES = {
    "intfloat/multilingual-e5-small": {"prefix": "query: ", "license": "MIT", "params_m": 118},
    "intfloat/multilingual-e5-base": {"prefix": "query: ", "license": "MIT", "params_m": 278},
    "intfloat/multilingual-e5-large": {"prefix": "query: ", "license": "MIT", "params_m": 560},
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": {
        "prefix": "",
        "license": "Apache-2.0",
        "params_m": 278,
    },
    "sentence-transformers/LaBSE": {"prefix": "", "license": "Apache-2.0", "params_m": 471},
    "BAAI/bge-m3": {"prefix": "", "license": "MIT", "params_m": 568},
}


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score_pos > score_neg), ties count half."""
    p = pos[:, None]
    n = neg[None, :]
    return float(((p > n).sum() + 0.5 * (p == n).sum()) / (len(pos) * len(neg)))


def best_f1(pos: np.ndarray, neg: np.ndarray) -> tuple[float, float, float, float]:
    best = (0.0, 0.0, 0.0, 0.0)
    for t in np.unique(np.concatenate([pos, neg])):
        tp = (pos >= t).sum()
        fp = (neg >= t).sum()
        fn = (pos < t).sum()
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn)
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        if f1 > best[0]:
            best = (float(f1), float(t), float(prec), float(rec))
    return best


def evaluate(name: str, meta: dict, data: dict, device: str) -> dict:
    import torch
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    model = SentenceTransformer(name, device=device)
    load_s = time.time() - t0
    groups = {}
    all_rep, all_prog, all_unrel = [], [], []
    enc_s = 0.0
    for g, items in data.items():
        texts = []
        for it in items:
            texts += [it["anchor"], it["repeat"], it["progress"]]
        t0 = time.time()
        e = model.encode(
            [meta["prefix"] + t for t in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )
        enc_s += time.time() - t0
        a, r, p = e[0::3], e[1::3], e[2::3]
        rep = np.einsum("ij,ij->i", a, r)
        prog = np.einsum("ij,ij->i", a, p)
        # unrelated: anchor i vs repeat/progress of every other item j in the group
        unrel = np.array(
            [a[i] @ x[j] for i in range(len(a)) for j in range(len(a)) if i != j for x in (r, p)]
        )
        groups[g] = {
            "n": len(items),
            "auc_repeat_vs_progress": round(auc(rep, prog), 3),
            "auc_repeat_vs_unrelated": round(auc(rep, unrel), 3),
            "mean_repeat": round(float(rep.mean()), 3),
            "mean_progress": round(float(prog.mean()), 3),
            "mean_unrelated": round(float(unrel.mean()), 3),
            "min_repeat": round(float(rep.min()), 3),
            "max_progress": round(float(prog.max()), 3),
        }
        all_rep.append(rep)
        all_prog.append(prog)
        all_unrel.append(unrel)
    rep, prog, unrel = map(np.concatenate, (all_rep, all_prog, all_unrel))
    f1, thr, prec, rec = best_f1(rep, np.concatenate([prog, unrel]))
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return {
        "model": name,
        "license": meta["license"],
        "params_m": meta["params_m"],
        "prefix": meta["prefix"],
        "auc_repeat_vs_progress": round(auc(rep, prog), 3),
        "auc_repeat_vs_unrelated": round(auc(rep, unrel), 3),
        "margin_repeat_minus_progress": round(float(rep.mean() - prog.mean()), 3),
        "best_f1": round(f1, 3),
        "threshold": round(thr, 3),
        "precision_at_threshold": round(prec, 3),
        "recall_at_threshold": round(rec, 3),
        "load_s": round(load_s, 1),
        "encode_s": round(enc_s, 2),
        "groups": groups,
    }


def choose(results: list[dict]) -> dict:
    ranked = sorted(results, key=lambda r: -r["auc_repeat_vs_progress"])
    best = ranked[0]
    close = [
        r for r in ranked if best["auc_repeat_vs_progress"] - r["auc_repeat_vs_progress"] <= 0.01
    ]
    return min(close, key=lambda r: r["params_m"])


def write_report(results: list[dict], chosen: dict, device: str) -> None:
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "embedding_benchmark.json").write_text(
        json.dumps(
            {"device": device, "chosen": chosen["model"], "results": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    lines = [
        "# Embedding model benchmark (Phase 3)",
        "",
        f"Generated by `scripts/embedding_benchmark.py` on {platform.node()} ({device}), "
        f"Python {sys.version.split()[0]}.",
        "",
        "**Data:** `scripts/bench/embedding_pairs.yaml` — 40 hand-written creator-style items "
        "(EN, Hindi, Hinglish in Roman and Devanagari, and English↔Hinglish cross-language). "
        "AI-assisted, not taken from real transcripts, so treat the ranking "
        "as indicative and the threshold as **provisional** until checked on real videos.",
        "",
        "**Question:** does the model score a reworded *repeat* of a point higher than a "
        "*same-topic* sentence that adds new information? That is the distinction the "
        "repetition and information-gain features depend on.",
        "",
        "**Selection rule (fixed before running):** highest overall AUC repeat-vs-progress; "
        "within 0.01, prefer the smaller model.",
        "",
        "| Model | Licence | Params (M) | AUC rep vs progress | AUC rep vs unrelated | "
        "Margin | Best F1 | Threshold | Encode s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: -r["auc_repeat_vs_progress"]):
        mark = " **(chosen)**" if r is chosen else ""
        lines.append(
            f"| `{r['model']}`{mark} | {r['license']} | {r['params_m']} | "
            f"{r['auc_repeat_vs_progress']} | {r['auc_repeat_vs_unrelated']} | "
            f"{r['margin_repeat_minus_progress']} | {r['best_f1']} | {r['threshold']} | "
            f"{r['encode_s']} |"
        )
    lines += [
        "",
        "## Per group: AUC repeat vs progress",
        "",
        "| Model | " + " | ".join(chosen["groups"]) + " |",
        "|---|" + "---|" * len(chosen["groups"]),
    ]
    for r in sorted(results, key=lambda r: -r["auc_repeat_vs_progress"]):
        lines.append(
            f"| `{r['model']}` | "
            + " | ".join(str(g["auc_repeat_vs_progress"]) for g in r["groups"].values())
            + " |"
        )
    lines += [
        "",
        "## Chosen model, per group detail",
        "",
        "| Group | n | mean repeat | mean progress | mean unrelated | min repeat | "
        "max progress |",
        "|---|---|---|---|---|---|---|",
    ]
    for g, v in chosen["groups"].items():
        lines.append(
            f"| {g} | {v['n']} | {v['mean_repeat']} | {v['mean_progress']} | "
            f"{v['mean_unrelated']} | {v['min_repeat']} | {v['max_progress']} |"
        )
    lines += [
        "",
        f"At the chosen threshold {chosen['threshold']}: precision "
        f"{chosen['precision_at_threshold']}, recall {chosen['recall_at_threshold']} "
        "(repeat vs progress+unrelated, on this small set).",
        "",
    ]
    (docs / "embedding_benchmark.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=list(CANDIDATES))
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()
    import torch

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    results = []
    for m in args.models:
        print(f"== {m}", flush=True)
        try:
            r = evaluate(m, CANDIDATES[m], data, device)
        except Exception as e:  # report and continue; a missing model shouldn't hide the others
            print(f"   FAILED: {type(e).__name__}: {e}", flush=True)
            continue
        print(
            f"   AUC rep/prog={r['auc_repeat_vs_progress']} rep/unrel="
            f"{r['auc_repeat_vs_unrelated']} thr={r['threshold']} f1={r['best_f1']}",
            flush=True,
        )
        results.append(r)
    chosen = choose(results)
    write_report(results, chosen, device)
    print(f"chosen: {chosen['model']} threshold={chosen['threshold']}")


if __name__ == "__main__":
    main()
