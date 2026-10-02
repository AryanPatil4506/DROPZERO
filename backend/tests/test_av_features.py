"""Audio/visual feature maths on synthetic signals (test inputs for DSP, not fake speech data)."""

import numpy as np
import pytest

from backend.app.config import load_config
from backend.app.features.audio.energy import frame_db, segment_audio, silence_threshold_db
from backend.app.features.av import detect_cuts, extract_av_features
from backend.app.features.visual.scenes import frame_diffs, scene_cuts, segment_visual
from backend.app.segmentation.windows import segment_transcript
from backend.tests.conftest import fixture_transcript

SR = 16000


@pytest.fixture
def cfg():
    return load_config("av_features")


def _frames(spec, fps=2.0, h=36, w=64):
    """spec: list of (seconds, value or 'noise')."""
    rng = np.random.default_rng(0)
    out = []
    for secs, val in spec:
        for _ in range(int(secs * fps)):
            if val == "noise":
                out.append(rng.integers(0, 256, (h, w), dtype=np.uint8))
            else:
                out.append(np.full((h, w), val, dtype=np.uint8))
    return np.stack(out)


def test_hard_cut_detected(cfg):
    frames = _frames([(10, 20), (10, 220), (10, 20)])
    cuts = scene_cuts(frame_diffs(frames), 2.0, cfg["visual"])
    assert cuts == [10.0, 20.0]


def test_steady_motion_is_not_a_cut(cfg):
    # slow fade: every frame changes a bit, none should be a cut
    frames = np.stack([np.full((36, 64), v, dtype=np.uint8) for v in range(0, 240, 4)])
    assert scene_cuts(frame_diffs(frames), 2.0, cfg["visual"]) == []


def test_noisy_footage_is_not_a_cut_stream(cfg):
    frames = _frames([(20, "noise")])
    assert scene_cuts(frame_diffs(frames), 2.0, cfg["visual"]) == []  # local median guard


def test_segment_visual_static_and_since_cut(cfg):
    frames = _frames([(10, 20), (20, 220)])
    diffs = frame_diffs(frames)
    cuts = scene_cuts(diffs, 2.0, cfg["visual"])
    v = segment_visual(diffs, cuts, 2.0, 12.0, 24.0, cfg["visual"])
    assert v.scene_cut_count == 0 and v.static_ratio == 1.0
    assert v.longest_static_s == 12.0
    assert v.seconds_since_cut == 14.0  # last cut at 10 s, segment ends at 24 s
    with_cut = segment_visual(diffs, cuts, 2.0, 0.0, 12.0, cfg["visual"])
    assert with_cut.scene_cut_count == 1 and with_cut.cuts_per_minute == 5.0
    assert segment_visual(diffs, cuts, 2.0, 100.0, 110.0, cfg["visual"]) is None


def _tone(secs, amp):
    t = np.arange(int(secs * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_silence_is_relative_to_video_loudness(cfg):
    a = cfg["audio"]
    for amp in (0.5, 0.01):  # loud mic and quiet mic give the same silence ratio
        samples = np.concatenate([_tone(5, amp), np.zeros(5 * SR, np.float32), _tone(5, amp)])
        db, hop = frame_db(samples, SR, a["frame_ms"], a["hop_ms"])
        thr = silence_threshold_db(db, a)
        med = float(np.median(db[db >= thr]))
        whole = segment_audio(db, hop, thr, med, 0.0, 15.0)
        assert whole.silence_ratio == pytest.approx(1 / 3, abs=0.01)
        # only the edge frame overlapping the tone at 10 s can count as voiced
        assert segment_audio(db, hop, thr, med, 5.0, 10.0).silence_ratio >= 0.98
        assert segment_audio(db, hop, thr, med, 0.0, 5.0).energy_db == pytest.approx(0, abs=0.1)


def test_quieter_section_is_negative_energy(cfg):
    a = cfg["audio"]
    samples = np.concatenate([_tone(10, 0.4), _tone(10, 0.1)])
    db, hop = frame_db(samples, SR, a["frame_ms"], a["hop_ms"])
    thr = silence_threshold_db(db, a)
    med = float(np.median(db[db >= thr]))
    quiet = segment_audio(db, hop, thr, med, 10.0, 20.0)
    loud = segment_audio(db, hop, thr, med, 0.0, 10.0)
    assert loud.energy_db - quiet.energy_db == pytest.approx(20 * np.log10(4), abs=0.1)
    assert quiet.energy_db < 0 < loud.energy_db


def test_extract_av_features_aligned_and_deterministic(cfg):
    t = fixture_transcript("en")
    dur = t.duration_s
    frames = _frames([(60, 30), (dur - 60 + 1, 200)])
    diffs, cuts = detect_cuts(frames, cfg)
    assert cuts == [60.0]
    segs = segment_transcript(t, load_config("segmentation")["windows"], boundary_hints=cuts)
    samples = _tone(dur, 0.3)

    def run():
        return extract_av_features("p", segs, samples, diffs, cuts, True, cfg)

    fs = run()
    assert [s.segment_id for s in fs.segments] == [s.id for s in segs]
    assert sum(s.scene_cut_count for s in fs.segments) == 1
    assert run().model_dump() == fs.model_dump()
    audio_only = extract_av_features("p", segs, samples, np.zeros(0), [], False, cfg)
    assert all(s.static_ratio is None and s.silence_ratio is not None for s in audio_only.segments)


def test_scene_cut_becomes_segment_boundary(cfg):
    t = fixture_transcript("en")
    w = load_config("segmentation")["windows"]
    base = {round(s.end, 1) for s in segment_transcript(t, w)}
    # pick a sentence end that is not already a boundary and pretend a cut happens there
    target = next(s.end for s in t.sentences[4:] if round(s.end, 1) not in base)
    hinted = segment_transcript(t, w, boundary_hints=[target])
    assert any(abs(s.end - target) <= w["hint_tolerance_s"] for s in hinted)
