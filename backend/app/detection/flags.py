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
from backend.app.schemas.flags import (
    Edit,
    Evidence,
    Flag,
    FlagsResponse,
    PromiseCheck,
    PromiseItem,
)
from backend.app.schemas.prediction import Prediction
from backend.app.schemas.segment import Segment
from backend.app.schemas.transcript import Transcript

RULES_VERSION = "rules-1.7"

# Only CUTs are simulated: under the exposure model, removed time removes its drop risk. MOVE,
# SHORTEN, REWRITE and ADD_VISUAL are advice (the model has no notion of reordering or visuals).


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


def _runs(items, pred):
    """Consecutive items for which pred is true, as lists."""
    runs, cur = [], []
    for x in items:
        if pred(x):
            cur.append(x)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def snap_to_pause(t: float, words, window: float) -> float:
    """If a cut point falls inside a word, move it to the nearer pause around that word (within
    window s). Points already in a pause are left alone."""
    for i, w in enumerate(words):
        if w.start < t < w.end:
            before = (words[i - 1].end + w.start) / 2 if i > 0 else w.start
            after = (w.end + words[i + 1].start) / 2 if i + 1 < len(words) else w.end
            best = min((before, after), key=lambda x: abs(x - t))
            return round(best, 3) if abs(best - t) <= window else t
    return t


class _Builder:
    def __init__(self, words=None, snap_window: float = 0.0) -> None:
        self.flags: list[Flag] = []
        self.edits: list[Edit] = []
        self.words = words or []
        self.snap_window = snap_window

    def flag(self, **kw: Any) -> Flag:
        f = Flag(id=f"f{len(self.flags) + 1}", **kw)
        self.flags.append(f)
        return f

    def edit(self, f: Flag, **kw: Any) -> None:
        if kw["action"] == "CUT" and self.words and self.snap_window > 0:
            a = snap_to_pause(kw["start"], self.words, self.snap_window)
            b = snap_to_pause(kw["end"], self.words, self.snap_window)
            if b > a:
                kw["start"], kw["end"] = a, b
        e = Edit(
            id=f"e{len(self.edits) + 1}",
            flag_id=f.id,
            simulatable=kw["action"] == "CUT",
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
    ledger: list[PromiseItem] | None = None,
) -> FlagsResponse:
    b = _Builder(t.words, cfg["cuts"]["snap_window_s"])
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
    title_words = len(promise.title.split())
    if title_words >= pc["min_title_words"] and (
        promise.first_mention_s is None or promise.first_mention_s > pc["late_after_s"]
    ):
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

    # ---- repetition: judged against THIS video's own similarity baseline (a single-topic
    # lecture is similar to itself everywhere), at most max_flags, strongest first
    rc = cfg["repetition"]
    sims = [feats[s.index].repetition_similarity for s in speech]
    sims = [x for x in sims if x is not None]
    rep_thr = rc["flag_threshold"]
    if sims:
        rep_thr = max(rep_thr, float(np.quantile(sims, rc["video_quantile"])))
    cands = []
    for s in speech:
        fe = feats[s.index]
        if fe.repetition_similarity is None or fe.repetition_similarity < rep_thr:
            continue
        m = segments[fe.repetition_match_segment]
        # a section echoing the title promise is the payoff, not a repeat. Judge by the matched
        # SENTENCES when we have them: a segment that merely contains the promise line can
        # still be repeated for other reasons (e.g. a definition right after the question).
        fm = promise.first_mention_s
        if fm is not None:
            ms = fe.repetition_matches
            if ms and all(x.matched_start <= fm < x.matched_end + 1e-6 for x in ms):
                continue
            if not ms and m.start <= fm < m.end:
                continue
        cands.append((s, fe, m))
    cands = sorted(cands, key=lambda x: -x[1].repetition_similarity)[: rc["max_flags"]]
    for s, fe, m in sorted(cands, key=lambda x: x[0].start):
        ev = [
            Evidence(
                label="Similarity to earlier section",
                value=fe.repetition_similarity,
                ref_start=m.start,
                ref_end=m.end,
            ),
            Evidence(
                label="This video's usual similarity (90th percentile)", value=round(rep_thr, 4)
            ),
        ]
        if fe.semantic_novelty is not None:
            ev.append(
                Evidence(label="New information vs everything before", value=fe.semantic_novelty)
            )
        f = b.flag(
            start=s.start,
            end=s.end,
            severity="high" if fe.repetition_similarity >= rc["high_threshold"] else "medium",
            category="repetition",
            source=src(True, s.start, s.end),
            risk_score=round(min(1.0, fe.repetition_similarity), 3),
            title=f"Repeats {mmss(m.start)}–{mmss(m.end)}",
            explanation=f"This section says much the same as {mmss(m.start)}–{mmss(m.end)} "
            f"(similarity {fe.repetition_similarity}, above this video's usual level).",
            evidence=ev,
        )
        # smallest range that removes the repeat: matched sentences, clipped to this segment
        lo_s = s.speech_start if s.speech_start is not None else s.start
        hi_s = s.speech_end if s.speech_end is not None else s.end
        cut_lo = max(lo_s, min((x.start for x in fe.repetition_matches), default=lo_s))
        cut_hi = min(hi_s, max((x.end for x in fe.repetition_matches), default=hi_s))
        if cut_hi - cut_lo < 1.0:
            cut_lo, cut_hi = lo_s, hi_s
        b.edit(
            f,
            action="CUT",
            start=cut_lo,
            end=cut_hi,
            reason=f"Cut {mmss(cut_lo)}–{mmss(cut_hi)}: repeats {mmss(m.start)}–{mmss(m.end)}",
        )

    # ---- low new information: runs below an absolute AND this video's own low level
    lc = cfg["low_information"]
    gains_all = [feats[s.index].information_gain for s in speech]
    gains_all = [g for g in gains_all if g is not None]
    gain_thr = lc["gain_threshold"]
    if gains_all:
        gain_thr = min(gain_thr, float(np.quantile(gains_all, lc["video_quantile"])))

    def low_gain(s: Segment) -> bool:
        g = feats[s.index].information_gain
        return g is not None and g < gain_thr

    for run in _runs(speech, low_gain):
        lo, hi = run[0].start, run[-1].end
        if hi - lo < lc["min_run_s"]:
            continue
        gains = [feats[x.index].information_gain for x in run]
        f = b.flag(
            start=lo,
            end=hi,
            severity="medium",
            category="low_information",
            source=src(True, lo, hi),
            risk_score=0.5,
            title=f"Little new information for {hi - lo:.0f} s",
            explanation=f"{mmss(lo)}–{mmss(hi)} adds little beyond the previous minute, even by "
            "this video's own standard.",
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

    # ---- slow pacing: merged runs of segments long enough to judge
    pace_cfg = cfg["pacing"]

    def slow(s: Segment) -> bool:
        p = feats[s.index].pace_ratio
        return (
            s.kind == "speech"
            and s.end - s.start >= pace_cfg["min_segment_s"]
            and p is not None
            and p < pace_cfg["slow_ratio"]
        )

    for run in _runs(segments, slow):
        lo, hi = run[0].start, run[-1].end
        slowest = min(feats[x.index].pace_ratio for x in run)
        f = b.flag(
            start=lo,
            end=hi,
            severity="medium",
            category="pacing",
            source=src(True, lo, hi),
            risk_score=0.4,
            title="Slower than your average pace",
            explanation=f"Speaking rate drops to {slowest:.0%} of this video's own average.",
            evidence=[
                Evidence(label="Slowest pace vs your average", value=slowest),
                Evidence(label="Duration", value=round(hi - lo, 1), unit="s"),
            ],
        )
        b.edit(f, action="SHORTEN", start=lo, end=hi, reason="Tighten pauses or trim this section")

    # ---- long stretches without speech: consecutive silence segments merged into one flag
    sil_cfg = cfg["silence"]
    speech_s = sum((s.speech_end or s.end) - (s.speech_start or s.start) for s in speech)
    speech_share = speech_s / max(t.duration_s, 1e-6)
    music_led = speech_share < sil_cfg["music_led_speech_share"]
    for run in _runs(segments, lambda s: s.kind == "silence" and s.start >= hook_end):
        lo, hi = run[0].start, run[-1].end
        if hi - lo < sil_cfg["mid_video_silence_s"]:
            continue
        quiet = [
            av_by[x.index].silence_ratio
            for x in run
            if x.index in av_by and av_by[x.index].silence_ratio is not None
        ]
        dead_air = bool(quiet) and float(np.mean(quiet)) >= sil_cfg["dead_air_silence_ratio"]
        if not quiet:  # script mode / no audio analysis: fall back to the speech-only view
            dead_air = not music_led
        if not dead_air and hi - lo < sil_cfg["music_min_s"]:
            continue  # music / visuals without speech: only long stretches are worth a flag
        if dead_air:
            title = f"{hi - lo:.0f} s of dead air"
            expl = "No speech and almost no sound here; viewers have nothing to hold on to."
            ev_extra = (
                [
                    Evidence(
                        label="Share of this stretch that is silent audio",
                        value=round(float(np.mean(quiet)), 3),
                    )
                ]
                if quiet
                else []
            )
        else:
            title = f"{hi - lo:.0f} s of music/visuals without speech"
            expl = (
                "Music or visuals carry this stretch without speech. Fine if something worth "
                "watching is on screen; long stretches risk losing viewers."
            )
            ev_extra = [Evidence(label="Share of video with speech", value=round(speech_share, 3))]
        f = b.flag(
            start=lo,
            end=hi,
            severity="medium",
            category="silence",
            source=src(True, lo, hi),
            risk_score=0.6 if dead_air else 0.3,
            title=title,
            explanation=expl,
            evidence=[Evidence(label="No speech for", value=round(hi - lo, 1), unit="s")]
            + ev_extra,
        )
        b.edit(
            f,
            action="CUT",
            start=lo + 0.5,
            end=hi - 0.5,
            reason=f"Trim {mmss(lo)}–{mmss(hi)} to a short beat",
        )

    # ---- static picture
    for s in segments:
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

    # ---- promise ledger: promises made in the opening that pay off late, or never
    for pr in ledger or []:
        if pr.source != "intro" or pr.status == "kept":
            continue
        ev = [Evidence(label="Promise", value=pr.text, ref_start=pr.made_at, ref_end=pr.made_end)]
        if pr.status == "late":
            ev += [
                Evidence(
                    label="Paid off at",
                    value=round(pr.payoff_at, 1),
                    unit="s",
                    ref_start=pr.payoff_at,
                    ref_end=pr.payoff_end,
                ),
                Evidence(label="Delay", value=pr.delay_s, unit="s"),
                Evidence(label="Payoff match (similarity)", value=pr.similarity),
            ]
            title = (
                f"Promise at {mmss(pr.made_at)} kept only at {mmss(pr.payoff_at)} "
                f"({mmss(pr.delay_s)} later)"
            )
            expl = (
                "Viewers were promised something early and wait a long time for it; many leave "
                "before the payoff."
            )
        else:
            title = f"Promise at {mmss(pr.made_at)} is never clearly paid off"
            expl = (
                "An open loop: the video promises something it never visibly delivers, which "
                "costs trust and watch time."
            )
        f = b.flag(
            start=pr.made_at,
            end=pr.made_end,
            severity="high" if pr.status == "open" else "medium",
            category="payoff_delay",
            source=src(True, pr.made_at, pr.made_end),
            risk_score=0.7 if pr.status == "open" else 0.6,
            title=title,
            explanation=expl,
            evidence=ev,
        )
        if pr.status == "late":
            b.edit(
                f,
                action="MOVE",
                start=pr.payoff_at,
                end=pr.payoff_end,
                target_time=pr.made_end,
                reason=f"Preview the payoff ({mmss(pr.payoff_at)}) right after the promise, "
                "then explain how",
                rewrite_text=pr.payoff_text,
            )
        else:
            b.edit(
                f,
                action="REWRITE",
                start=pr.made_at,
                end=pr.made_end,
                reason="Deliver what this line promises, or drop the promise",
            )

    # ---- model-only high risk
    if cfg["model"]["flag_model_only"]:
        covered = [(f.start, f.end) for f in b.flags]
        only_model = [
            r
            for r in pred.segments
            if r.risk == "high" and not any(lo < r.end and hi > r.start for lo, hi in covered)
        ]
        keep = {r.index for r in sorted(only_model, key=lambda r: -r.p_drop)[:3]}
        for r in pred.segments:
            if r.index not in keep:
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
        ledger=ledger or [],
        flags=flags,
        edits=b.edits,
    )


__all__ = ["detect", "promise_check", "mmss", "RULES_VERSION"]
