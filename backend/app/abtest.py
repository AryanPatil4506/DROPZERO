"""Hook A/B simulator: compare two script versions before recording.

Each version runs through the real pipeline in memory (script mode: timing is estimated; nothing
is stored). Versions are compared on hook signals that mean the same thing across two scripts,
plus the model-estimated curve. A curve difference smaller than the model's uncertainty band is
reported as "no clear difference". This is a simulation, never a real A/B test with viewers.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from backend.app.config import load_config
from backend.app.detection.flags import detect, promise_check
from backend.app.detection.promises import build_ledger
from backend.app.features.text.embedder import Embedder
from backend.app.features.text.extract import extract_text_features
from backend.app.model.predict import predict
from backend.app.schemas.prediction import CurvePoint
from backend.app.schemas.project import Language
from backend.app.segmentation.windows import segment_transcript
from backend.app.transcription.script_timing import estimate_transcript

LABEL = (
    "Simulated comparison of two script versions (model-estimated, timing estimated from word "
    "counts). Not a real A/B test with viewers."
)
HOOK_S = 30.0


class ABRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    language: Language
    script_a: str = Field(min_length=20, max_length=200_000)
    script_b: str = Field(min_length=20, max_length=200_000)
    name_a: str = "Version A"
    name_b: str = "Version B"


class Metric(BaseModel):
    key: str
    label: str
    a: float | str | None
    b: float | str | None
    better: Literal["lower", "higher", "info"]
    winner: Literal["a", "b", "tie", "n/a"]
    note: str | None = None


class Variant(BaseModel):
    name: str
    duration_s: float
    points: list[CurvePoint]
    hook_flags: list[str]


class ABResult(BaseModel):
    label: str
    a: Variant
    b: Variant
    metrics: list[Metric]
    summary: str


def _at(points: list[CurvePoint], t: float) -> tuple[float, float, float]:
    """Retention, lower, upper at time t (linear interpolation)."""
    ts = [p.t for p in points]
    t = min(t, ts[-1])
    return tuple(
        float(np.interp(t, ts, [getattr(p, k) for p in points]))
        for k in ("retention", "lower", "upper")
    )


def _analyse(text: str, title: str, lang: Language, emb: Embedder) -> dict:
    seg = load_config("segmentation")
    t = estimate_transcript(text, "ab", lang, seg["script_timing"], seg["sentences"])
    segs = segment_transcript(t, seg["windows"])
    tf = extract_text_features(t, segs, emb, load_config("text_features"), load_config("fillers"))
    pred = predict(segs, tf, t.duration_s)
    det_cfg = load_config("detection")
    pc = promise_check(title, t, emb, det_cfg["promise"])
    ledger = build_ledger(t, pc, emb, load_config("promises"))
    flags = detect(t, segs, tf, pred, pc, det_cfg, None, ledger)
    return signals(t, segs, tf, pred, flags, None)


def signals(t, segs, tf, pred, flags, av) -> dict:
    """Hook signals from analysed results (a script analysed in memory, or a stored project)."""
    pc, ledger = flags.promise, flags.ledger
    hook = [f for f in tf.segments if f.start < HOOK_S and f.kind == "speech"]
    paces = [f.pace_ratio for f in hook if f.pace_ratio is not None]
    hook_promises = [p for p in ledger if p.source == "intro" and p.made_at < HOOK_S]
    return {
        "t": t,
        "pred": pred,
        "r30": _at(pred.points, HOOK_S),
        "r60": _at(pred.points, 60.0),
        "title_at": pc.first_mention_s,
        "fillers": sum(f.filler_count for f in hook),
        "pace": round(float(np.mean(paces)), 3) if paces else None,
        "promise": hook_promises[0].status if hook_promises else "none",
        # only flags with a concrete cause; vague model-only flags don't decide a hook comparison
        "flags60": [f for f in flags.flags if f.start < 60.0 and f.category != "model_risk"],
        # video only: seconds without speech in the hook, and scene cuts in the hook
        "dead_air": (
            round(
                sum(
                    min(s.end, HOOK_S) - s.start
                    for s in segs
                    if s.kind == "silence" and s.start < HOOK_S
                ),
                1,
            )
            if av
            else None
        ),
        "cuts": sum(c < HOOK_S for c in av.scene_cuts) if av and av.has_video else None,
    }


def _cmp(a, b, better: str, tol: float = 0.0) -> str:
    if a is None or b is None:
        return "n/a"
    if a == b or abs(a - b) <= tol:  # a == b also covers "never" vs "never" (inf - inf)
        return "tie"
    return ("a" if a < b else "b") if better == "lower" else ("a" if a > b else "b")


_PROMISE_RANK = {"kept": 3, "late": 2, "open": 1, "none": 0}


def compare(req: ABRequest, emb: Embedder) -> ABResult:
    va = _analyse(req.script_a, req.title, req.language, emb)
    vb = _analyse(req.script_b, req.title, req.language, emb)
    return compare_signals(va, vb, req.name_a, req.name_b, LABEL)


def compare_signals(va: dict, vb: dict, name_a: str, name_b: str, label: str) -> ABResult:
    metrics: list[Metric] = []
    for key, mlabel in (
        ("r30", "Model-estimated retention at 0:30"),
        ("r60", "Model-estimated retention at 1:00"),
    ):
        (ra, la, ua), (rb, lb, ub) = va[key], vb[key]
        # a difference inside the model's uncertainty is not a difference
        tol = min(ua - la, ub - lb) / 2
        w = _cmp(ra, rb, "higher", tol)
        metrics.append(
            Metric(
                key=key,
                label=mlabel,
                a=round(ra, 3),
                b=round(rb, 3),
                better="higher",
                winner=w,
                note=None if w != "tie" else "difference smaller than the model's uncertainty",
            )
        )
    metrics.append(
        Metric(
            key="title_at",
            label="Title addressed after (s)",
            a=_r(va["title_at"]),
            b=_r(vb["title_at"]),
            better="lower",
            winner=_cmp(_inf(va["title_at"]), _inf(vb["title_at"]), "lower", 2.0),
        )
    )
    metrics.append(
        Metric(
            key="fillers",
            label="Filler words in the first 30 s",
            a=va["fillers"],
            b=vb["fillers"],
            better="lower",
            winner=_cmp(va["fillers"], vb["fillers"], "lower"),
        )
    )
    metrics.append(
        Metric(
            key="pace",
            label="Hook pace vs the script's own average",
            a=va["pace"],
            b=vb["pace"],
            better="higher",
            winner=_cmp(va["pace"], vb["pace"], "higher", 0.05),
        )
    )
    metrics.append(
        Metric(
            key="promise",
            label="Promise made in the hook",
            a=va["promise"],
            b=vb["promise"],
            better="higher",
            winner=_cmp(_PROMISE_RANK[va["promise"]], _PROMISE_RANK[vb["promise"]], "higher"),
        )
    )
    if va.get("dead_air") is not None and vb.get("dead_air") is not None:
        metrics.append(
            Metric(
                key="dead_air",
                label="Seconds without speech in the first 30 s",
                a=va["dead_air"],
                b=vb["dead_air"],
                better="lower",
                winner=_cmp(va["dead_air"], vb["dead_air"], "lower", 1.0),
            )
        )
    if va.get("cuts") is not None and vb.get("cuts") is not None:
        metrics.append(
            Metric(
                key="cuts",
                label="Scene cuts in the first 30 s",
                a=va["cuts"],
                b=vb["cuts"],
                better="higher",
                winner=_cmp(va["cuts"], vb["cuts"], "higher"),
            )
        )
    na, nb = len(va["flags60"]), len(vb["flags60"])
    metrics.append(
        Metric(
            key="flags60",
            label="Problems found in the first minute",
            a=na,
            b=nb,
            better="lower",
            winner=_cmp(na, nb, "lower"),
        )
    )
    wins_a = sum(m.winner == "a" for m in metrics)
    wins_b = sum(m.winner == "b" for m in metrics)
    if wins_a == wins_b:
        summary = "No clear winner: the versions trade off; see each signal."
    else:
        lead, n, other = (name_a, wins_a, wins_b) if wins_a > wins_b else (name_b, wins_b, wins_a)
        summary = f"{lead} leads on {n} of {len(metrics)} signals (the other leads on {other})."
    if all(m.winner == "tie" for m in metrics[:2]):
        summary += " The predicted curves are within the model's uncertainty of each other."

    def variant(name: str, v: dict) -> Variant:
        return Variant(
            name=name,
            duration_s=v["t"].duration_s,
            points=v["pred"].points,
            hook_flags=[f.title for f in v["flags60"]],
        )

    return ABResult(
        label=label,
        a=variant(name_a, va),
        b=variant(name_b, vb),
        metrics=metrics,
        summary=summary,
    )


def _r(x):
    return None if x is None else round(float(x), 1)


def _inf(x):
    return float("inf") if x is None else x


PROJECT_LABEL = (
    "Comparison of two analysed projects (model-estimated curves; signals measured on each "
    "upload). Not a real A/B test with viewers."
)
