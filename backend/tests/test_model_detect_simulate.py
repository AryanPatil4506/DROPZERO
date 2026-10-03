import numpy as np
import pytest

from backend.app.config import load_config
from backend.app.detection.flags import detect, mmss
from backend.app.features.text.extract import extract_text_features
from backend.app.model.features import (
    curve_from_hazard,
    hazard_to_rate,
    rate_to_hazard,
    segment_hazard,
)
from backend.app.model.predict import load_model, predict
from backend.app.schemas.flags import Edit, PromiseCheck
from backend.app.segmentation.windows import segment_transcript
from backend.app.simulate.edits import apply_edits, resolve, simulate
from backend.tests.conftest import fixture_transcript
from backend.tests.helpers import HashingEmbedder

# ---------- model maths


def test_rate_roundtrip_and_slicing_invariance():
    h = np.array([0.0, 0.1, 0.5, 0.9])
    d = np.array([10.0, 12.0, 8.0, 15.0])
    assert np.allclose(rate_to_hazard(hazard_to_rate(h, d), d), h, atol=1e-9)
    # one 20 s segment at rate r == two 10 s segments at rate r
    r = np.array([0.02])
    one = curve_from_hazard(rate_to_hazard(r, np.array([20.0])))[-1]
    two = curve_from_hazard(rate_to_hazard(np.repeat(r, 2), np.array([10.0, 10.0])))[-1]
    assert one == pytest.approx(two)


def test_segment_hazard_from_curve():
    t = fixture_transcript("en")
    segs = segment_transcript(t, load_config("segmentation")["windows"])
    ret = np.linspace(1.0, 0.5, int(t.duration_s) + 1)
    h = segment_hazard(segs, ret)
    assert len(h) == len(segs) and np.all((h >= 0) & (h <= 1))
    assert curve_from_hazard(h)[-1] == pytest.approx(ret[-2] / ret[0], abs=0.02)


def _pipeline(lang="en"):
    t = fixture_transcript(lang)
    segs = segment_transcript(t, load_config("segmentation")["windows"])
    fs = extract_text_features(
        t, segs, HashingEmbedder(), load_config("text_features"), load_config("fillers")
    )
    return t, segs, fs


def test_prediction_shape_band_and_determinism():
    t, segs, fs = _pipeline()
    p = predict(segs, fs, t.duration_s)
    assert p.model_version == load_model()["version"] and "not YouTube analytics" in p.label
    r = [x.retention for x in p.points]
    assert r[0] == 1.0 and all(a >= b for a, b in zip(r, r[1:], strict=False))
    assert all(x.lower <= x.retention <= x.upper for x in p.points)
    assert len(p.segments) == len(segs) and {s.risk for s in p.segments} <= {
        "low",
        "medium",
        "high",
    }
    assert predict(segs, fs, t.duration_s).model_dump() == p.model_dump()


# ---------- detector


def _promise(first=None):
    return PromiseCheck(
        title="I Built an AI Agent in 24 Hours",
        first_mention_s=first,
        first_mention_text="x" if first is not None else None,
        best_match_s=first,
        best_similarity=0.5 if first else 0.2,
    )


def test_slow_hook_and_missing_promise_flags():
    t, segs, fs = _pipeline("en")  # 18 s silent intro
    pred = predict(segs, fs, t.duration_s)
    res = detect(t, segs, fs, pred, _promise(None), load_config("detection"))
    cats = {f.category for f in res.flags}
    assert {"slow_hook", "payoff_delay"} <= cats
    hook = next(f for f in res.flags if f.category == "slow_hook")
    cut = next(e for e in res.edits if e.flag_id == hook.id and e.action == "CUT")
    assert cut.start == 0.0 and cut.end == pytest.approx(t.words[0].start - 0.5)
    for f in res.flags:  # every flag is timestamped, evidenced, explained and sourced
        assert (
            f.end > f.start
            and f.evidence
            and f.explanation
            and f.source in ("model", "rule", "model+rule")
        )
    assert all(e.simulatable == (e.action == "CUT") for e in res.edits)


def test_repetition_flag_and_payoff_exception():
    t, segs, fs = _pipeline("en")
    pred = predict(segs, fs, t.duration_s)
    cfg = load_config("detection")
    sp = [s for s in segs if s.kind == "speech"]
    earlier, later = sp[2], sp[-3]
    f = fs.segments[later.index]
    f.repetition_similarity, f.repetition_match_segment = 0.75, earlier.index
    f.repetition_matches = []  # segment-level fallback of the payoff rule
    res = detect(t, segs, fs, pred, _promise(1.0), cfg)
    rep = next(x for x in res.flags if x.category == "repetition" and x.start == later.start)
    assert rep.severity == "high"
    assert rep.title == f"Repeats {mmss(earlier.start)}–{mmss(earlier.end)}"
    # if the matched section is where the title promise is first addressed -> payoff, no flag
    res2 = detect(t, segs, fs, pred, _promise(earlier.start + 0.1), cfg)
    assert not [x for x in res2.flags if x.category == "repetition" and x.start == later.start]


# ---------- simulation


def _edit(i, action, s, e, target=None):
    return Edit(
        id=i,
        flag_id="f",
        action=action,
        start=s,
        end=e,
        target_time=target,
        reason="r",
        simulatable=action in ("CUT", "MOVE"),
    )


def test_cut_and_move_timeline():
    t = fixture_transcript("en")
    sent = load_config("segmentation")["sentences"]
    cut = apply_edits(t, [_edit("e1", "CUT", 50.0, 60.0)], sent)
    assert cut.duration_s == pytest.approx(t.duration_s - 10.0, abs=1e-3)
    inside = sum(50.0 <= (w.start + w.end) / 2 < 60.0 for w in t.words)
    assert inside > 0 and len(cut.words) == len(t.words) - inside
    s = t.sentences[5]
    moved = apply_edits(t, [_edit("e2", "MOVE", s.start, s.end, target=0.0)], sent)
    assert moved.duration_s == pytest.approx(t.duration_s)
    assert [w.text for w in moved.words[: s.word_end - s.word_start]] == [
        w.text for w in t.words[s.word_start : s.word_end]
    ]
    starts = [w.start for w in moved.words]
    assert starts == sorted(starts)


def test_resolve_skips_overlaps_and_advice():
    kept, skipped = resolve(
        [
            _edit("e1", "CUT", 10, 20),
            _edit("e2", "CUT", 15, 25),
            _edit("e3", "REWRITE", 30, 40),
            _edit("e4", "MOVE", 50, 55, target=12),
        ]
    )
    assert [e.id for e in kept] == ["e1"] and sorted(skipped) == ["e2", "e3", "e4"]


def test_simulate_labels_and_shortens():
    t, segs, fs = _pipeline("en")
    pred = predict(segs, fs, t.duration_s)
    cfgs = {k: load_config(k) for k in ("segmentation", "text_features", "fillers")}
    edits = [_edit("e1", "CUT", 0.0, 17.5)]
    sim = simulate(t, edits, ["e1"], pred.points, HashingEmbedder(), cfgs)
    assert "Simulated" in sim.label and "guaranteed" in sim.label
    assert sim.applied_edit_ids == ["e1"]
    assert sim.simulated_duration_s == pytest.approx(t.duration_s - 17.5, abs=0.01)
    assert sim.original == pred.points


# ---------- simulation v2 (exposure)


def test_exposure_simulation_cut_trim_speed():
    from backend.app.simulate.exposure import CustomEdit, simulate_exposure

    t, segs, fs = _pipeline("en")
    pred = predict(segs, fs, t.duration_s)
    art = load_model()
    cut = _edit("e1", "CUT", 60.0, 75.0)
    sim = simulate_exposure(segs, fs, t.duration_s, pred.points, [cut], ["e1"], [], art)
    assert sim.applied_edit_ids == ["e1"]
    assert sim.simulated_duration_s == pytest.approx(t.duration_s - 15.0, abs=0.01)
    assert sim.delta["end_retention_pp"] >= 0  # removing exposure can only help this model
    # untouched content before the cut keeps exactly its predicted retention
    before = [p for p in pred.points if p.t <= 60.0]
    assert [p.retention for p in sim.simulated[: len(before)]] == [p.retention for p in before]
    trims = [
        CustomEdit(action="TRIM_START", start=0, end=10),
        CustomEdit(action="SPEED", start=100, end=140, factor=2.0),
    ]
    sim2 = simulate_exposure(segs, fs, t.duration_s, pred.points, [], [], trims, art)
    assert sim2.simulated_duration_s == pytest.approx(t.duration_s - 10 - 20, abs=0.01)
    assert len(sim2.applied_custom) == 2 and "Simulated" in sim2.label
    move = _edit("e2", "MOVE", 80.0, 85.0, target=0.0)
    sim3 = simulate_exposure(segs, fs, t.duration_s, pred.points, [move], ["e2"], [], art)
    assert sim3.skipped_edit_ids == ["e2"]


def test_snap_to_pause_only_moves_points_inside_words():
    from backend.app.detection.flags import snap_to_pause
    from backend.app.schemas.transcript import Word

    w = [
        Word(text="a", start=1.0, end=2.0),
        Word(text="b", start=2.4, end=3.0),
        Word(text="c", start=5.0, end=6.0),
    ]
    assert snap_to_pause(0.5, w, 1.5) == 0.5  # already in a pause
    assert snap_to_pause(4.0, w, 1.5) == 4.0
    assert snap_to_pause(1.9, w, 1.5) == 2.2  # inside "a" -> pause after it
    assert snap_to_pause(2.5, w, 1.5) == 2.2  # inside "b" -> pause before it


def test_payoff_rule_uses_matched_sentences():
    """A repeat whose matched sentence is NOT the promise line is flagged even when the earlier
    segment also contains the promise line."""
    from backend.app.schemas.features import RepetitionMatch

    t, segs, fs = _pipeline("en")
    pred = predict(segs, fs, t.duration_s)
    cfg = load_config("detection")
    sp = [s for s in segs if s.kind == "speech"]
    earlier, later = sp[2], sp[-3]
    f = fs.segments[later.index]
    f.repetition_similarity, f.repetition_match_segment = 0.75, earlier.index
    promise_at = earlier.start + 0.1
    other = RepetitionMatch(
        sentence_idx=0,
        start=later.start,
        end=later.end,
        matched_sentence_idx=0,
        matched_start=earlier.start + 2.0,
        matched_end=earlier.end,
        similarity=0.8,
    )
    f.repetition_matches = [other]
    res = detect(t, segs, fs, pred, _promise(promise_at), cfg)
    assert [x for x in res.flags if x.category == "repetition" and x.start == later.start]
    same = other.model_copy(
        update={"matched_start": earlier.start, "matched_end": earlier.start + 1}
    )
    f.repetition_matches = [same]
    res2 = detect(t, segs, fs, pred, _promise(promise_at), cfg)
    assert not [x for x in res2.flags if x.category == "repetition" and x.start == later.start]
