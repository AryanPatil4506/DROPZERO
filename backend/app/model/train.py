"""Train and validate the retention-risk model on real lecture-viewing curves (MOOCCubeX).

Pipeline per lecture: captions -> Transcript -> the app's own segmenter -> the app's own text
features (LaBSE) -> feature matrix; target = observed per-segment drop probability.
Split: by lecture (fixed hash), never by segment. Thresholds are chosen on train only.

    python -m backend.app.model.train            (scripts/train_model.py wraps this)
"""

import json
import pickle  # only our own locally produced artifacts are loaded; never untrusted files
import time
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from backend.app.config import config_hash, load_config
from backend.app.features.text.embedder import SentenceTransformerEmbedder
from backend.app.features.text.extract import extract_text_features
from backend.app.model.features import (
    FEATURES,
    GROUPS,
    MODEL_COLS,
    curve_from_hazard,
    durations_of,
    feature_matrix,
    hazard_to_rate,
    rate_to_hazard,
    segment_hazard,
    signed_segment_rate,
)
from backend.app.model.predict import (
    band_lookup,
    band_offsets,
    calibrated_curve,
    drop_probs,
    position_rate,
)
from backend.app.segmentation.windows import segment_transcript
from backend.app.settings import REPO_ROOT
from backend.app.validation.mooc_adapter import captions_to_transcript
from backend.app.versions import FEATURE_SCHEMA_VERSION

DATA = REPO_ROOT / "data" / "processed" / "mooc"
MODELS = REPO_ROOT / "models"


# ---------------------------------------------------------------- dataset


def build_dataset(cache: Path) -> list[dict]:
    """One dict per lecture with X, hazard, segment times, actual R at segment ends. Cached."""
    text_cfg, fill_cfg = load_config("text_features"), load_config("fillers")
    win_cfg = load_config("segmentation")["windows"]
    key = config_hash(
        [
            text_cfg,
            fill_cfg,
            win_cfg,
            FEATURES,
            FEATURE_SCHEMA_VERSION,
            (DATA / "summary.json").read_text(encoding="utf-8"),
        ]
    )
    if cache.exists():
        with cache.open("rb") as f:
            obj = pickle.load(f)
        if obj["key"] == key:
            return obj["lectures"]
    curves = {}
    with (DATA / "curves.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            curves[r["ccid"]] = r
    emb = SentenceTransformerEmbedder(text_cfg["embedding"], "auto")
    lectures = []
    t0 = time.time()
    with (DATA / "captions.jsonl").open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            rec = json.loads(line)
            c = curves.get(rec["ccid"])
            if c is None:
                continue
            t = captions_to_transcript(rec, c["duration_s"])
            segs = segment_transcript(t, win_cfg)
            fs = extract_text_features(t, segs, emb, text_cfg, fill_cfg)
            ret = np.array(c["retention"])
            lectures.append(
                {
                    "ccid": c["ccid"],
                    "split": c["split"],
                    "n_starters": c["n_starters"],
                    "duration_s": t.duration_s,
                    "X": feature_matrix(segs, fs, t.duration_s),
                    "hazard": segment_hazard(segs, ret),
                    "starts": np.array([s.start for s in segs]),
                    "ends": np.array([s.end for s in segs]),
                    "actual_R": np.array(
                        [ret[min(len(ret) - 1, max(0, int(np.ceil(s.end)) - 1))] for s in segs]
                    ),
                    "retention": ret,
                }
            )
            if i % 100 == 0:
                print(f"  features: {len(lectures)} lectures ({time.time()-t0:.0f}s)", flush=True)
    with cache.open("wb") as f:
        pickle.dump({"key": key, "lectures": lectures}, f)
    return lectures


# ---------------------------------------------------------------- models


def _hgb(cfg: dict, **kw) -> HistGradientBoostingRegressor:
    m = cfg["model"]
    return HistGradientBoostingRegressor(
        max_iter=m["max_iter"],
        learning_rate=m["learning_rate"],
        max_leaf_nodes=m["max_leaf_nodes"],
        min_samples_leaf=m["min_samples_leaf"],
        l2_regularization=m["l2_regularization"],
        random_state=m["random_state"],
        early_stopping=False,
        **kw,
    )


def mono_cst(cols: list[int], cfg: dict) -> list[int]:
    """Direction constraints from research priors (config/model.yaml -> monotonic)."""
    m = cfg.get("monotonic", {})
    return [m.get(FEATURES[i], 0) for i in cols]


def fit(lectures: list[dict], cols: list[int], cfg: dict):
    """Per-second drop rate on the signed target (keeps re-watching), direction-constrained."""
    X = np.vstack([lec["X"][:, cols] for lec in lectures])
    y = np.concatenate([signed_rate(lec) for lec in lectures])
    return _hgb(cfg, monotonic_cst=mono_cst(cols, cfg)).fit(X, y)


def signed_rate(lec: dict) -> np.ndarray:
    return signed_segment_rate(lec["starts"], lec["ends"], lec["retention"])


def fit_drop_classifier(lectures: list[dict], cfg: dict):
    major = cfg["detection"]["major_drop_hazard"]
    X = np.vstack([lec["X"][1:, MODEL_COLS] for lec in lectures])
    y = np.concatenate([(lec["hazard"][1:] >= major).astype(int) for lec in lectures])
    m = cfg["model"]
    return HistGradientBoostingClassifier(
        max_iter=m["max_iter"],
        learning_rate=m["learning_rate"],
        max_leaf_nodes=m["max_leaf_nodes"],
        min_samples_leaf=m["min_samples_leaf"],
        l2_regularization=m["l2_regularization"],
        random_state=m["random_state"],
        early_stopping=False,
    ).fit(X, y)


def drop_rate_by_position(lectures, cfg) -> list[float]:
    bins = cfg["baseline"]["position_bins"]
    major = cfg["detection"]["major_drop_hazard"]
    i_rs = FEATURES.index("rel_start")
    hits, n = np.zeros(bins), np.zeros(bins)
    for lec in lectures:
        for x, h in zip(lec["X"][1:], lec["hazard"][1:], strict=True):
            b = min(bins - 1, int(x[i_rs] * bins))
            n[b] += 1
            hits[b] += h >= major
    return [float(max(h / max(c, 1), 1e-3)) for h, c in zip(hits, n, strict=True)]


class PositionBaseline:
    """Category-average curve: mean observed hazard by relative position (+ first segment)."""

    def __init__(self, bins: int):
        self.bins = bins

    def fit(self, lectures):
        first, by_bin = [], [[] for _ in range(self.bins)]
        i_rs, i_first = FEATURES.index("rel_start"), FEATURES.index("is_first")
        for lec in lectures:
            rates = hazard_to_rate(lec["hazard"], durations_of(lec["X"]))
            for x, h in zip(lec["X"], rates, strict=True):
                if x[i_first]:
                    first.append(h)
                else:
                    by_bin[min(self.bins - 1, int(x[i_rs] * self.bins))].append(h)
        self.first = float(np.mean(first))
        overall = float(np.mean([h for b in by_bin for h in b]))
        self.table = [float(np.mean(b)) if b else overall for b in by_bin]
        return self

    def predict(self, X):
        """Segment drop probability."""
        return rate_to_hazard(self.predict_rate(X), durations_of(X))

    def predict_rate(self, X):
        i_rs, i_first = FEATURES.index("rel_start"), FEATURES.index("is_first")
        return np.array(
            [
                (
                    self.first
                    if x[i_first]
                    else self.table[min(self.bins - 1, int(x[i_rs] * self.bins))]
                )
                for x in X
            ]
        )


# ---------------------------------------------------------------- evaluation


def _drops(lec, hazard, thr):
    """Indices of non-first segments with hazard >= thr."""
    return [i for i in range(1, len(hazard)) if hazard[i] >= thr]


def detection(lectures, preds, pred_thr, cfg):
    d = cfg["detection"]
    tol, major = d["tolerance_s"], d["major_drop_hazard"]
    tp_actual = total_actual = tp_pred = total_pred = 0
    delays = []
    per = []
    for lec, p in zip(lectures, preds, strict=True):
        act = _drops(lec, lec["hazard"], major)
        prd = _drops(lec, p, pred_thr)
        s, e = lec["starts"], lec["ends"]

        def near(i, j, s=s, e=e):
            return s[i] - tol <= e[j] and s[j] <= e[i] + tol

        hit_a = [a for a in act if any(near(a, q) for q in prd)]
        hit_p = [q for q in prd if any(near(a, q) for a in act)]
        for a in hit_a:
            delays.append(min(abs(s[q] - s[a]) for q in prd if near(a, q)))
        tp_actual += len(hit_a)
        total_actual += len(act)
        tp_pred += len(hit_p)
        total_pred += len(prd)
        per.append({"actual": act, "detected": hit_a, "predicted": prd})
    prec = tp_pred / total_pred if total_pred else 0.0
    rec = tp_actual / total_actual if total_actual else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {
        "precision": round(prec, 3),
        "recall": round(rec, 3),
        "f1": round(f1, 3),
        "detected": tp_actual,
        "total": total_actual,
        "predicted": total_pred,
        "median_delay_s": round(float(np.median(delays)), 1) if delays else None,
    }, per


def pick_threshold(lectures, preds, cfg) -> float:
    cands = np.quantile(np.concatenate([p[1:] for p in preds]), np.linspace(0.5, 0.99, 50))
    best = max(cands, key=lambda t: (detection(lectures, preds, t, cfg)[0]["f1"], -t))
    return float(best)


def curve_metrics(lectures, preds):
    act = np.concatenate([lec["actual_R"] for lec in lectures])
    prd = np.concatenate([curve_from_hazard(p) for p in preds])
    haz_a = np.concatenate([lec["hazard"][1:] for lec in lectures])
    haz_p = np.concatenate([p[1:] for p in preds])
    within = [
        spearmanr(lec["hazard"][1:], p[1:]).statistic
        for lec, p in zip(lectures, preds, strict=True)
        if len(p) > 3 and np.std(lec["hazard"][1:]) > 0 and np.std(p[1:]) > 0
    ]
    return {
        "mae": round(float(np.mean(np.abs(act - prd))), 4),
        "rmse": round(float(np.sqrt(np.mean((act - prd) ** 2))), 4),
        "pearson": round(float(pearsonr(act, prd).statistic), 3),
        "spearman": round(float(spearmanr(act, prd).statistic), 3),
        # harder, more honest: does it rank WHICH segments lose viewers (intro excluded)?
        "hazard_spearman_pooled": round(float(spearmanr(haz_a, haz_p).statistic), 3),
        "hazard_spearman_within_video_mean": round(float(np.nanmean(within)), 3),
    }


def predict_all(model, lectures, cols):
    return [
        rate_to_hazard(np.clip(model.predict(lec["X"][:, cols]), 0, None), durations_of(lec["X"]))
        for lec in lectures
    ]


# ---------------------------------------------------------------- main


def main() -> None:
    cfg = load_config("model")
    MODELS.mkdir(exist_ok=True)
    t0 = time.time()
    lectures = build_dataset(DATA / "dataset.pkl")
    train = [lec for lec in lectures if lec["split"] == "train"]
    test = [lec for lec in lectures if lec["split"] == "test"]
    print(
        f"dataset: {len(train)} train / {len(test)} test lectures, "
        f"{sum(len(lec['hazard']) for lec in lectures):,} segments ({time.time()-t0:.0f}s)"
    )
    all_cols = MODEL_COLS
    version = (
        "mooc-hgb3-"
        + config_hash(
            [cfg, FEATURES, MODEL_COLS, FEATURE_SCHEMA_VERSION, [lec["ccid"] for lec in train]]
        )[:8]
    )

    model = fit(train, all_cols, cfg)
    base = PositionBaseline(cfg["baseline"]["position_bins"]).fit(train)
    clf = fit_drop_classifier(train, cfg)

    # calibration of the cumulative curve level, fitted on TRAIN only
    p_tr = predict_all(model, train, all_cols)
    # one global rate multiplier k: R_cal = R_raw ** k (smooth, keeps R(0) = 1, so simulated
    # edits change the curve continuously). Fitted on TRAIN by least squares over a grid.
    raw_tr = np.concatenate([curve_from_hazard(p) for p in p_tr])
    act_tr = np.concatenate([lec["actual_R"] for lec in train])
    ks = np.linspace(0.1, 2.0, 191)
    k = float(ks[np.argmin([np.mean((raw_tr**k - act_tr) ** 2) for k in ks])])
    iso = {"k": round(k, 3)}
    print(f"calibration rate multiplier k = {k:.3f}")
    art = {"model": model, "calib": iso}
    q_lo, q_hi = cfg["model"]["band_quantiles"]
    band = band_offsets(train, art, cfg["model"]["band_bins"], q_lo, q_hi)

    def as_hazard(r):  # per-segment drop implied by a monotone curve
        prev = np.concatenate([[1.0], r[:-1]])
        return np.clip(1 - r / np.maximum(prev, 1e-9), 0, 1)

    c_te = [calibrated_curve(art, lec["X"]) for lec in test]
    p_te = [as_hazard(r) for r in c_te]
    b_tr = [base.predict(lec["X"]) for lec in train]
    b_te = [base.predict(lec["X"]) for lec in test]
    # drop detection: dedicated classifier, threshold chosen on TRAIN
    d_tr = [drop_probs(clf, lec["X"]) for lec in train]
    d_te = [drop_probs(clf, lec["X"]) for lec in test]
    thr_model = pick_threshold(train, d_tr, cfg)
    thr_base = pick_threshold(train, b_tr, cfg)
    det_model, per_model = detection(test, d_te, thr_model, cfg)
    det_base, _ = detection(test, b_te, thr_base, cfg)

    inside = total = 0
    for lec, r in zip(test, c_te, strict=True):
        lo_r = r + band_lookup(band, lec["X"], "lo")
        hi_r = r + band_lookup(band, lec["X"], "hi")
        inside += int(np.sum((lec["actual_R"] >= lo_r) & (lec["actual_R"] <= hi_r)))
        total += len(lec["actual_R"])

    ablations = {}
    for g, names in GROUPS.items():
        cols = [i for i in MODEL_COLS if FEATURES[i] not in names]
        m = fit(train, cols, cfg)
        pt = predict_all(m, train, cols)
        pe = predict_all(m, test, cols)
        cm = curve_metrics(test, pe)
        ablations[g] = {
            "mae": cm["mae"],
            "hazard_spearman_pooled": cm["hazard_spearman_pooled"],
            "detection_f1": detection(test, pe, pick_threshold(train, pt, cfg), cfg)[0]["f1"],
        }

    # risk = drop probability relative to how often THIS position drops in training lectures
    drop_base = drop_rate_by_position(train, cfg)
    ratios = np.concatenate(
        [drop_probs(clf, lec["X"])[1:] / position_rate(drop_base, lec["X"])[1:] for lec in train]
    )
    risk = {
        "high": float(np.quantile(ratios, cfg["risk_levels"]["high_quantile"])),
        "medium": float(np.quantile(ratios, cfg["risk_levels"]["medium_quantile"])),
    }

    examples = []
    for lec, r, per in sorted(
        zip(test, c_te, per_model, strict=True), key=lambda z: -z[0]["n_starters"]
    )[:6]:
        examples.append(
            {
                "video_id": lec["ccid"],
                "title": f"Lecture {lec['ccid'][:8]} " f"({lec['n_starters']} viewers)",
                "actual": [
                    {"t": float(e), "retention": round(float(a), 4)}
                    for e, a in zip(lec["ends"], lec["actual_R"], strict=True)
                ],
                "predicted": [
                    {"t": float(e), "retention": round(float(x), 4)}
                    for e, x in zip(lec["ends"], r, strict=True)
                ],
                "drops": [
                    {"t": float(lec["starts"][i]), "detected": i in per["detected"]}
                    for i in per["actual"]
                ],
            }
        )

    summary = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    report = {
        "dataset": "MOOCCubeX lecture-viewing logs: real in-video drop-off of "
        f"{summary['viewers_read']:,} viewers on Chinese online-course lectures (not YouTube)",
        "model_version": version,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "n_videos_train": len(train),
        "n_videos_test": len(test),
        "split": "held out by lecture (fixed hash); thresholds chosen on train only",
        "metrics": curve_metrics(test, p_te),
        "baseline": {
            "name": "Category-average curve (mean drop by position)",
            **curve_metrics(test, b_te),
        },
        "detection": {
            "tolerance_s": cfg["detection"]["tolerance_s"],
            "major_drop_hazard": cfg["detection"]["major_drop_hazard"],
            **det_model,
        },
        "baseline_detection": det_base,
        "band": {"quantiles": [q_lo, q_hi], "test_coverage": round(inside / total, 3)},
        "level": {
            "median_end_retention_actual": round(
                float(np.median([x["actual_R"][-1] for x in test])), 3
            ),
            "median_end_retention_predicted": round(float(np.median([r[-1] for r in c_te])), 3),
        },
        "detector": "dedicated drop classifier (major drop = a segment losing >= 5% of its "
        "viewers); curve = calibrated rate model",
        "ablations": ablations,
        "examples": examples,
    }
    with (MODELS / "retention_model.pkl").open("wb") as f:
        pickle.dump(
            {
                "version": version,
                "features": FEATURES,
                "model_cols": MODEL_COLS,
                "model": model,
                "calib": iso,
                "band": band,
                "clf": clf,
                "drop_base": drop_base,
                "risk_thresholds": risk,
                "drop_threshold": thr_model,
                "baseline": base,
            },
            f,
        )
    (MODELS / "validation.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "model_version",
                    "metrics",
                    "baseline",
                    "detection",
                    "baseline_detection",
                    "band",
                    "level",
                    "ablations",
                )
            },
            indent=1,
        )
    )
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
