"""Step 6: drop-off detector + evidence engine + rule-based edit suggestions.

Two sources, always labelled on each flag:
- model: segments the retention model rates "high" (validated on held-out lecture data);
- rule: problem-statement causes measured directly (repetition, late title promise, slow hook,
  low new information, slow pacing, silence, static picture). Rules are NOT validated against
  retention data.
Explanations here are deterministic templates whose numbers all come from the flag's evidence.
"""

from typing import Any

import numpy as np

from backend.app.features.text.embedder import Embedder
from backend.app.schemas.av_features import AVFeatureSet
from backend.app.schemas.features import TextFeatureSet
from backend.app.schemas.flags import Edit, Evidence, Flag, FlagsResponse, PromiseCheck
from backend.app.schemas.prediction import Prediction
from backend.app.schemas.segment import Segment
from backend.app.schemas.transcript import Transcript

RULES_VERSION = "rules-1.0"


def mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


def promise_check(title: str, t: Transcript, embedder: Embedder, cfg: dict) -> PromiseCheck:
    if not t.sentences or not title.strip():
        return PromiseCheck(
            title=title,
            first_mention_s=None,
            first_mention_text=None,
            best_match_s=None,
            best_similarity=None,
        )
    e = embedder.embed([title] + [s.text for s in t.sentences])
    sims = e[1:] @ e[0]
    first = next((i for i, s in enumerate(sims) if s >= cfg["mention_threshold"]), None)
    # the title itself is often read out as the first line; that is not a payoff
    if first is not None and first == 0 and sims[0] > 0.9:
        first = next((i for i, s in enumerate(sims[1:], 1) if s >= cfg["mention_threshold"]), None)
    best = int(np.argmax(sims))
    return PromiseCheck(
        title=title,
        first_mention_s=t.sentences[first].start if first is not None else None,
        first_mention_text=t.sentences[first].text if first is not None else None,
        best_match_s=t.sentences[best].start,
        best_similarity=round(float(sims[best]), 4),
    )


class _Builder:
    def __init__(self) -> None:
        self.flags: list[Flag] = []
        self.edits: list[Edit] = []

    def flag(self, **kw: Any) -> Flag:
        f = Flag(id=f"f{len(self.flags) + 1}", **kw)
        self.flags.append(f)
        return f

    def edit(self, f: Flag, **kw: Any) -> None:
        e = Edit(
            id=f"e{len(self.edits) + 1}",
            flag_id=f.id,
            simulatable=kw["action"] in ("CUT", "MOVE"),
            **kw,
        )
        self.edits.append(e)
        f.edit_ids.append(e.id)


def detect(
    t: Transcript,
    segments: list[Segment],
    tf: TextFeatureSet,
    pred: Prediction,
    promise: PromiseCheck,
    cfg: dict,
    av: AVFeatureSet | None = None,
) -> FlagsResponse:
    b = _Builder()
    feats = {f.index: f for f in tf.segments}
    av_by = {a.index: a for a in av.segments} if av else {}
    speech = [s for s in segments if s.kind == "speech"]
    first_speech = speech[0].speech_start if speech else 0.0

    def model_part(lo: float, hi: float) -> tuple[bool, float]:
        rs = [r for r in pred.segments if r.start < hi and r.end > lo]
        return any(r.risk == "high" for r in rs), max((r.p_drop for r in rs), default=0.0)

    def src(rule: bool, lo: float, hi: float) -> str:
        m, _ = model_part(lo, hi)
        return "model+rule" if m and rule else "model" if m else "rule"

    # ---- slow hook: silent lead-in, fillers in the first window
    hk = cfg["hook"]
    hook_end = min(hk["window_s"], t.duration_s)
    hook_words = [w for w in t.words if w.start < hook_end]
    hook_fillers = sum(f.filler_count for f in tf.segments if f.start < hook_end)
    filler_ratio = hook_fillers / len(hook_words) if hook_words else 0.0
    ev, reasons = [], []
    if first_speech >= hk["lead_silence_s"]:
        ev.append(Evidence(label="No speech before", value=round(first_speech, 1), unit="s"))
        reasons.append(f"nothing is said for the first {first_speech:.0f} s")
    if filler_ratio >= hk["filler_ratio"]:
        ev.append(Evidence(label="Filler words in the first 30 s", value=hook_fillers))
        reasons.append(f"{hook_fillers} filler words in the first {hook_end:.0f} s")
    if ev:
        f = b.flag(
            start=0.0,
            end=hook_end,
            severity="high",
            category="slow_hook",
            source=src(True, 0, hook_end),
            risk_score=0.8,
            title=f"Slow hook: {reasons[0]}",
            explanation="The opening is where most viewers decide to leave; "
            + "; ".join(reasons)
            + ".",
            evidence=ev,
        )
        if first_speech >= hk["lead_silence_s"]:
            b.edit(
                f,
                action="CUT",
                start=0.0,
                end=max(0.0, first_speech - 0.5),
                reason=f"Cut the silent intro {mmss(0)}–{mmss(first_speech - 0.5)}",
            )
        if filler_ratio >= hk["filler_ratio"]:
            b.edit(
                f,
                action="REWRITE",
                start=0.0,
                end=hook_end,
                reason="Tighten the opening: remove filler words and channel housekeeping",
            )

    # ---- late title promise (payoff delay)
    pc = cfg["promise"]
    if promise.first_mention_s is None or promise.first_mention_s > pc["late_after_s"]:
        when = promise.first_mention_s
        high = when is None or when > pc["high_after_s"]
        lo, hi = 0.0, when if when is not None else min(60.0, t.duration_s)
        ev = [Evidence(label="Title", value=promise.title)]
        if when is not None:
            ev.append(
                Evidence(label="Title promise first addressed at", value=round(when, 1), unit="s")
            )
        if promise.best_similarity is not None:
            ev.append(
                Evidence(
                    label="Best title match (similarity)",
                    value=promise.best_similarity,
                    ref_start=promise.best_match_s,
                )
            )
        f = b.flag(
            start=lo,
            end=hi,
            severity="high" if high else "medium",
            category="payoff_delay",
            source=src(True, lo, hi),
            risk_score=0.75,
            title=(
                f"Title promise not addressed until {mmss(when)}"
                if when is not None
                else "The video never clearly addresses its title"
            ),
            explanation="Viewers clicked for the title; until it is addressed they have "
            "no reason to stay.",
            evidence=ev,
        )
        s = next((x for x in t.sentences if x.start <= (when or -1) < x.end + 1e-6), None)
        if s is not None:
            b.edit(
                f,
                action="MOVE",
                start=s.start,
                end=s.end,
                target_time=first_speech,
                reason=f"Move the line at {mmss(s.start)} to the opening as the hook",
                rewrite_text=s.text,
            )

    # ---- repetition (segment level, >= 20 s apart)
    rc = cfg["repetition"]
    for s in speech:
        fe = feats[s.index]
        if fe.repetition_similarity is None or fe.repetition_similarity < rc["flag_threshold"]:
            continue
        m = segments[fe.repetition_match_segment]
        # a section echoing the title promise is the payoff, not a repeat
        if promise.first_mention_s is not None and m.start <= promise.first_mention_s < m.end:
            continue
        ev = [
            Evidence(
                label="Similarity to earlier section",
                value=fe.repetition_similarity,
                ref_start=m.start,
                ref_end=m.end,
            )
        ]
        if fe.semantic_novelty is not None:
            ev.append(
                Evidence(label="New information vs everything before", value=fe.semantic_novelty)
            )
        if fe.repetition_count > 1:
            ev.append(Evidence(label="Earlier sections it resembles", value=fe.repetition_count))
        f = b.flag(
            start=s.start,
            end=s.end,
            severity="high" if fe.repetition_similarity >= rc["high_threshold"] else "medium",
            category="repetition",
            source=src(True, s.start, s.end),
            risk_score=round(min(1.0, fe.repetition_similarity), 3),
            title=f"Repeats {mmss(m.start)}–{mmss(m.end)}",
            explanation=f"This section says much the same as {mmss(m.start)}–"
            f"{mmss(m.end)} (similarity {fe.repetition_similarity}).",
            evidence=ev,
        )
        # smallest range that removes the repeat: the matched sentences in this segment
        ms = [x for x in fe.repetition_matches]
        cut_lo = min((x.start for x in ms), default=s.speech_start or s.start)
        cut_hi = max((x.end for x in ms), default=s.speech_end or s.end)
        b.edit(
            f,
            action="CUT",
            start=cut_lo,
            end=cut_hi,
            reason=f"Cut {mmss(cut_lo)}–{mmss(cut_hi)}: repeats {mmss(m.start)}–" f"{mmss(m.end)}",
        )

    # ---- low new information: consecutive speech segments with low gain
    lc = cfg["low_information"]
    run: list[Segment] = []
    for s in speech + [None]:
        g = feats[s.index].information_gain if s is not None else None
        if s is not None and g is not None and g < lc["gain_threshold"]:
            run.append(s)
            continue
        if run and run[-1].end - run[0].start >= lc["min_run_s"]:
            lo, hi = run[0].start, run[-1].end
            gains = [feats[x.index].information_gain for x in run]
            f = b.flag(
                start=lo,
                end=hi,
                severity="medium",
                category="low_information",
                source=src(True, lo, hi),
                risk_score=0.5,
                title=f"Little new information for {hi - lo:.0f} s",
                explanation=f"{mmss(lo)}–{mmss(hi)} adds little beyond the previous " "minute.",
                evidence=[
                    Evidence(label="Duration", value=round(hi - lo, 1), unit="s"),
                    Evidence(label="Lowest information gain", value=round(min(gains), 4)),
                ],
            )
            worst = min(run, key=lambda x: feats[x.index].information_gain)
            b.edit(
                f,
                action="SHORTEN",
                start=worst.start,
                end=worst.end,
                reason=f"Shorten {mmss(worst.start)}–{mmss(worst.end)}, the least new part",
            )
        run = []

    # ---- pacing, silence, visuals (per segment)
    for s in segments:
        fe = feats[s.index]
        if (
            s.kind == "speech"
            and fe.pace_ratio is not None
            and fe.pace_ratio < cfg["pacing"]["slow_ratio"]
        ):
            f = b.flag(
                start=s.start,
                end=s.end,
                severity="medium",
                category="pacing",
                source=src(True, s.start, s.end),
                risk_score=0.4,
                title="Slower than your average pace",
                explanation=f"Speaking rate here is {fe.pace_ratio:.0%} of this video's "
                "own average.",
                evidence=[Evidence(label="Pace vs your average", value=fe.pace_ratio)],
            )
            b.edit(
                f,
                action="SHORTEN",
                start=s.start,
                end=s.end,
                reason="Tighten pauses or trim this section",
            )
        if (
            s.kind == "silence"
            and s.start > hook_end
            and s.end - s.start >= cfg["silence"]["mid_video_silence_s"]
        ):
            f = b.flag(
                start=s.start,
                end=s.end,
                severity="medium",
                category="silence",
                source=src(True, s.start, s.end),
                risk_score=0.5,
                title=f"{s.end - s.start:.0f} s without speech",
                explanation="A long stretch with no speech; fine if something important "
                "is shown, otherwise viewers drift.",
                evidence=[
                    Evidence(label="No speech for", value=round(s.end - s.start, 1), unit="s")
                ],
            )
            b.edit(
                f,
                action="CUT",
                start=s.start + 0.5,
                end=s.end - 0.5,
                reason=f"Trim the silence {mmss(s.start)}–{mmss(s.end)}",
            )
        a = av_by.get(s.index)
        if a and a.longest_static_s is not None and a.longest_static_s >= cfg["visual"]["static_s"]:
            f = b.flag(
                start=s.start,
                end=s.end,
                severity="medium",
                category="visual_monotony",
                source=src(True, s.start, s.end),
                risk_score=0.4,
                title="Picture barely changes",
                explanation=f"The picture is almost static for {a.longest_static_s:.0f} s.",
                evidence=[
                    Evidence(label="Longest static stretch", value=a.longest_static_s, unit="s"),
                    Evidence(label="Seconds since last cut", value=a.seconds_since_cut, unit="s"),
                ],
            )
            b.edit(
                f,
                action="ADD_VISUAL",
                start=s.start,
                end=s.end,
                reason="Add B-roll, a screen recording or a cut here",
            )

    # ---- model-only high risk
    if cfg["model"]["flag_model_only"]:
        covered = [(f.start, f.end) for f in b.flags]
        for r in pred.segments:
            if r.risk != "high" or any(lo < r.end and hi > r.start for lo, hi in covered):
                continue
            b.flag(
                start=r.start,
                end=r.end,
                severity="medium",
                category="model_risk",
                source="model",
                risk_score=round(min(1.0, r.p_drop * 5), 3),
                title="Model-estimated drop risk, no single clear cause",
                explanation="The retention model rates this section high-risk, but no "
                "specific rule fired. Review it.",
                evidence=[Evidence(label="Model-estimated drop probability", value=r.p_drop)],
            )

    flags = sorted(b.flags, key=lambda f: (f.start, f.id))
    return FlagsResponse(
        project_id=t.project_id,
        model_version=pred.model_version,
        rules_version=RULES_VERSION,
        promise=promise,
        flags=flags,
        edits=b.edits,
    )


__all__ = ["detect", "promise_check", "mmss", "RULES_VERSION"]
