"""Hand-shaped mocks for endpoints that do not exist yet (prediction, flags, simulate, validation).

Shapes follow docs/frontend-brief.md section 4. Timestamps and evidence values come from the real
English sample (frontend/mock/en); every *predicted* number is a PLACEHOLDER and each file carries
"_mock". Never show these numbers in a pitch.

    python scripts/make_contract_mocks.py   (run scripts/export_api_samples.py first)
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "mock" / "en"
OUT = ROOT / "frontend" / "mock" / "contract"
MOCK = "MOCK DATA: shape only, numbers are placeholders. Do not present."


def load(name):
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def curve(p_drops, segs, band=0.04):
    pts, r = [{"t": 0.0, "retention": 1.0, "lower": 1.0, "upper": 1.0}], 1.0
    for k, (p, s) in enumerate(zip(p_drops, segs, strict=True)):
        r *= 1 - p
        w = band * math.sqrt(k + 1) / 3
        pts.append(
            {
                "t": s["end"],
                "retention": round(r, 4),
                "lower": round(max(0, r - w), 4),
                "upper": round(min(1, r + w), 4),
            }
        )
    return pts


def risk(p):
    return "high" if p >= 0.06 else "medium" if p >= 0.035 else "low"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    segs = load("segments.json")
    feats = {f["index"]: f for f in load("features_text.json")["segments"]}
    rep = max(
        (f for f in feats.values() if f["repetition_similarity"] is not None),
        key=lambda f: f["repetition_similarity"],
    )
    p = [0.03] * len(segs)
    p[0], p[1] = 0.09, 0.05  # placeholder: early drop
    p[rep["index"]] = 0.075
    pred = {
        "_mock": MOCK,
        "project_id": segs[0]["project_id"],
        "model_version": "mock-0",
        "feature_schema_version": "text-1.0",
        "timing_source": segs[0]["timing_source"],
        "label": "Model-estimated retention (DROPZERO internal score, not YouTube analytics)",
        "points": curve(p, segs),
        "segments": [
            {
                "segment_id": s["id"],
                "index": s["index"],
                "start": s["start"],
                "end": s["end"],
                "p_drop": p[i],
                "risk": risk(p[i]),
            }
            for i, s in enumerate(segs)
        ],
    }
    m = rep["repetition_matches"][0] if rep["repetition_matches"] else None
    flags = [
        {
            "id": "f1",
            "start": segs[0]["start"],
            "end": segs[1]["end"],
            "severity": "high",
            "category": "slow_hook",
            "risk_score": 0.82,
            "title": f"Intro runs {segs[1]['end']:.0f} s before the promised demo is mentioned",
            "explanation": "The first two segments are channel housekeeping (subscribe, bell) "
            "before the video says what the viewer will get.",
            "evidence": [
                {
                    "label": "Time to first statement of the video's value",
                    "value": segs[1]["start"],
                    "unit": "s",
                },
                {"label": "Filler words in intro", "value": feats[0]["filler_count"]},
            ],
            "secondary_categories": ["fillers"],
            "edit_ids": ["e1"],
        },
        {
            "id": "f2",
            "start": rep["start"],
            "end": rep["end"],
            "severity": "high",
            "category": "repetition",
            "risk_score": 0.77,
            "title": "This section repeats an earlier explanation",
            "explanation": "The definition of an agent is restated almost word for word.",
            "evidence": [
                {"label": "Similarity to earlier section", "value": rep["repetition_similarity"]},
                {"label": "Semantic novelty", "value": rep["semantic_novelty"]},
            ]
            + (
                [
                    {
                        "label": "Matches earlier",
                        "value": m["similarity"],
                        "ref_start": m["matched_start"],
                        "ref_end": m["matched_end"],
                    }
                ]
                if m
                else []
            ),
            "secondary_categories": ["low_information"],
            "edit_ids": ["e2"],
        },
    ]
    edits = [
        {
            "id": "e1",
            "flag_id": "f1",
            "action": "CUT",
            "start": segs[0]["start"],
            "end": segs[0]["end"],
            "target_time": None,
            "reason": "Cut the subscribe reminder; open with the demo promise.",
            "rewrite_text": None,
        },
        {
            "id": "e2",
            "flag_id": "f2",
            "action": "CUT",
            "start": rep["start"],
            "end": rep["end"],
            "target_time": None,
            "reason": "Repeated explanation of what an agent is.",
            "rewrite_text": None,
        },
    ]
    p_sim = [x for i, x in enumerate(p) if i not in (0, rep["index"])]
    kept = [s for i, s in enumerate(segs) if i not in (0, rep["index"])]
    shift, sim_segs = 0.0, []
    for i, s in enumerate(segs):
        if i in (0, rep["index"]):
            shift += s["end"] - s["start"]
            continue
        sim_segs.append({**s, "start": s["start"] - shift, "end": s["end"] - shift})
    simulate = {
        "_mock": MOCK,
        "label": "Simulated: model-estimated effect of these edits, not a guaranteed outcome",
        "applied_edit_ids": ["e1", "e2"],
        "original": pred["points"],
        "simulated": curve([max(0.02, x - 0.005) for x in p_sim], sim_segs),
        "original_duration_s": segs[-1]["end"],
        "simulated_duration_s": sim_segs[-1]["end"],
        "delta": {"end_retention_pp": 6.1, "avg_retention_pp": 4.3},
    }
    assert len(kept) == len(sim_segs)
    validation = {
        "_mock": MOCK,
        "dataset": "MOOCCubeX lecture viewing logs (real in-video drop-off; Chinese MOOC "
        "lectures, not YouTube)",
        "model_version": "mock-0",
        "n_videos_test": 120,
        "split": "held out by video",
        "metrics": {"mae": 0.061, "rmse": 0.083, "pearson": 0.71, "spearman": 0.68},
        "baseline": {
            "name": "Category-average curve",
            "mae": 0.094,
            "rmse": 0.121,
            "pearson": 0.52,
            "spearman": 0.49,
        },
        "detection": {
            "tolerance_s": 10,
            "precision": 0.64,
            "recall": 0.58,
            "f1": 0.61,
            "detected": 41,
            "total": 71,
        },
        "examples": [
            {
                "video_id": "V_example",
                "title": "Example lecture",
                "actual": [
                    {"t": t, "retention": round(math.exp(-t / 500), 3)} for t in range(0, 600, 15)
                ],
                "predicted": [
                    {"t": t, "retention": round(math.exp(-t / 450), 3)} for t in range(0, 600, 15)
                ],
                "drops": [{"t": 120, "detected": True}, {"t": 300, "detected": False}],
            }
        ],
    }
    for name, obj in [
        ("prediction.json", pred),
        ("flags.json", {"_mock": MOCK, "flags": flags, "edits": edits}),
        ("simulate.json", simulate),
        ("validation.json", validation),
    ]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", (OUT / name).relative_to(ROOT))


if __name__ == "__main__":
    main()
