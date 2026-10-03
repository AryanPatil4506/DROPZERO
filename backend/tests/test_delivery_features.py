"""Delivery evidence: pitch range (synthetic tones, test inputs for DSP), pauses between words,
repeated exact phrases (English, Hindi, Hinglish), and how they reach flags and scores."""

import numpy as np
import pytest

from backend.app.config import load_config
from backend.app.detection.flags import _delivery_evidence
from backend.app.features.audio.pitch import (
    pitch_range,
    segment_pitch,
    smooth_semitones,
    to_semitones,
    yin_f0,
)
from backend.app.features.av import extract_av_features
from backend.app.features.text.phrases import (
    phrase_occurrences,
    repeated_phrases,
    segment_pauses,
)
from backend.app.schemas.av_features import SegmentAVFeatures
from backend.app.schemas.features import PhraseRepeat
from backend.app.schemas.flags import Flag
from backend.app.schemas.segment import Segment
from backend.app.schemas.transcript import Word
from backend.tests.test_text_features import _features

SR = 16000
PCFG = load_config("av_features")["pitch"]


def _tone(f, secs, amp=0.3):
    t = np.arange(int(SR * secs)) / SR
    return amp * np.sin(2 * np.pi * f * t) + 0.1 * amp * np.sin(4 * np.pi * f * t)


def _glide(f0, semis, secs, amp=0.3):
    """Pitch moving smoothly up and down by +-semis around f0 (a lively voice, roughly)."""
    t = np.arange(int(SR * secs)) / SR
    f = f0 * 2 ** (semis * np.sin(2 * np.pi * 0.5 * t) / 12)
    return amp * np.sin(2 * np.pi * np.cumsum(f) / SR)


# ---------- pitch


@pytest.mark.parametrize("f", [85.0, 140.0, 230.0, 360.0])
def test_yin_finds_the_tone(f):
    f0, hop = yin_f0(_tone(f, 2.0), SR, PCFG)
    assert hop == pytest.approx(0.02)
    assert np.isnan(f0).mean() < 0.05
    assert np.nanmedian(f0) == pytest.approx(f, rel=0.005)


def test_noise_and_silence_are_unvoiced():
    noise = np.random.default_rng(0).normal(0, 0.1, SR * 2)
    assert np.isnan(yin_f0(noise, SR, PCFG)[0]).mean() > 0.95
    assert np.isnan(yin_f0(np.zeros(SR * 2), SR, PCFG)[0]).all()


def test_pitch_range_flat_vs_lively_and_deterministic():
    flat = to_semitones(yin_f0(_tone(150, 4.0), SR, PCFG)[0])
    lively = to_semitones(yin_f0(_glide(150, 6, 4.0), SR, PCFG)[0])
    assert pitch_range(flat[~np.isnan(flat)]) < 0.2
    assert 8.0 < pitch_range(lively[~np.isnan(lively)]) < 12.5
    again = to_semitones(yin_f0(_glide(150, 6, 4.0), SR, PCFG)[0])
    assert np.array_equal(np.isnan(lively), np.isnan(again))
    assert np.allclose(lively[~np.isnan(lively)], again[~np.isnan(again)])


def test_smoothing_removes_single_octave_jump():
    st = np.array([10.0, 10.0, 22.0, 10.0, 10.0, np.nan, 10.0])
    out = smooth_semitones(st, 5)
    assert out[2] == 10.0 and np.isnan(out[5])


def test_segment_pitch_needs_enough_voiced_speech():
    st = np.full(100, 5.0)
    voiced = np.zeros(100, dtype=bool)
    voiced[:50] = True  # 1 s at 20 ms hop
    p = segment_pitch(st, voiced, 0.02, 0.0, 2.0, min_voiced_s=2.0)
    assert p.pitch_range_st is None and p.voiced_s == 1.0
    voiced[:] = True
    assert segment_pitch(st, voiced, 0.02, 0.0, 2.0, 2.0).pitch_range_st == 0.0


def _seg(i, start, end, kind="speech"):
    return Segment(
        id=f"p:{i:04d}",
        project_id="p",
        index=i,
        start=start,
        end=end,
        kind=kind,
        word_start=0,
        word_end=0,
        sentence_ids=[],
        text="",
        speech_start=start if kind == "speech" else None,
        speech_end=end if kind == "speech" else None,
        boundary="sentence",
        timing_source="asr",
        segmenter_version="test",
    )


def test_flat_segment_is_measured_against_the_videos_own_range():
    audio = np.concatenate([_glide(140, 6, 10.0), _tone(140, 10.0), _glide(140, 6, 10.0)])
    segs = [_seg(0, 0.0, 10.0), _seg(1, 10.0, 20.0), _seg(2, 20.0, 30.0)]
    fs = extract_av_features("p", segs, audio, np.zeros(0), [], False, load_config("av_features"))
    flat, lively = fs.segments[1], fs.segments[0]
    assert flat.pitch_range_ratio < 0.1 and lively.pitch_range_ratio >= 1.0
    assert fs.pitch_median_hz == pytest.approx(140, rel=0.05)
    assert fs.pitch_range_median_st == lively.pitch_range_st


# ---------- pauses


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def test_pauses_between_words():
    words = [_w("a", 0.0, 0.4), _w("b", 0.5, 0.9), _w("c", 3.1, 3.5), _w("d", 5.2, 5.6)]
    p = segment_pauses(words, 1.5)
    assert p.longest_pause_s == 2.2 and p.longest_pause_at == 0.9 and p.long_pause_count == 2
    assert segment_pauses(words[:1], 1.5).longest_pause_s is None
    assert segment_pauses(words[:2], 1.5).long_pause_count == 0


def test_script_mode_has_no_pauses():
    t, segs, fs = _features("en")
    assert any(f.longest_pause_s is not None for f in fs.segments)
    from backend.app.features.text.extract import extract_text_features
    from backend.tests.helpers import HashingEmbedder

    est = t.model_copy(update={"timing_source": "estimated"})
    fs2 = extract_text_features(
        est, segs, HashingEmbedder(), load_config("text_features"), load_config("fillers")
    )
    assert all(f.longest_pause_s is None and f.long_pause_count == 0 for f in fs2.segments)


# ---------- repeated phrases

STOP = frozenset({"the", "a", "is", "ka", "hai", "है", "का"})
FILL = frozenset({"basically", "matlab"})
CFG = {"n": 3, "max_stopwords": 1}


def _occ(sentences):
    return phrase_occurrences([s.split() for s in sentences], FILL, STOP, CFG)


def test_longer_repeated_run_is_reported_once():
    s = ["we call the kernel now", "then we call the kernel now", "we call the kernel now ok"]
    occ = _occ(s)
    assert repeated_phrases(occ, 3) == ["we call the"]  # not also "call the kernel", ...


def test_fillers_break_phrases_and_stopword_heavy_grams_are_skipped():
    occ = _occ(["basically we go", "basically we go", "basically we go", "is the a", "is the a"])
    assert "basically we go" not in occ
    assert "is the a" not in occ


@pytest.mark.parametrize(
    "sentences, phrase",
    [
        (["system call ka use", "yeh system call ka", "phir system call ka"], "system call ka"),
        (["सिस्टम कॉल का काम", "यह सिस्टम कॉल का", "फिर सिस्टम कॉल का"], "सिस्टम कॉल का"),
    ],
)
def test_hinglish_and_hindi_phrases(sentences, phrase):
    occ = _occ(sentences)
    assert repeated_phrases(occ, 3) == [phrase]
    assert [o.sentence for o in occ[phrase]] == [0, 1, 2]


def test_extractor_reports_phrase_said_again_with_first_time():
    t, segs, fs = _features("en")
    stats = {p.phrase: p for p in fs.repeated_phrases}
    assert "out of 10" in stats and stats["out of 10"].count == 3
    reps = [r for f in fs.segments for r in f.phrase_repeats if r.phrase == "out of 10"]
    first = stats["out of 10"].times[0]
    assert reps and all(r.at > r.first_at == first for r in reps)


# ---------- evidence on flags


def _flag(category, start=0.0, end=10.0):
    return Flag(
        id="f",
        start=start,
        end=end,
        severity="medium",
        category=category,
        source="rule",
        risk_score=0.5,
        title="t",
        explanation="e",
        evidence=[],
    )


class _TF:
    def __init__(self, pause=None, at=None, reps=()):
        self.longest_pause_s, self.longest_pause_at, self.phrase_repeats = pause, at, list(reps)


def _av(ratio, st):
    return SegmentAVFeatures(
        segment_id="s0",
        index=0,
        start=0.0,
        end=10.0,
        silence_ratio=0.1,
        energy_db=0.0,
        energy_variation_db=3.0,
        pitch_range_st=st,
        pitch_range_ratio=ratio,
        scene_cut_count=None,
        cuts_per_minute=None,
        visual_change_mean=None,
        static_ratio=None,
        longest_static_s=None,
        seconds_since_cut=None,
    )


DCFG = load_config("detection")["delivery"]


def test_delivery_evidence_added_to_flags():
    rep = PhraseRepeat(phrase="out of 10", at=5.0, count=4, first_at=1.0)
    feats = {0: _TF(2.4, 3.0, [rep])}
    f = _flag("repetition")
    _delivery_evidence([f], [_seg(0, 0.0, 10.0)], feats, {0: _av(0.4, 1.8)}, DCFG)
    labels = {e.label: e.value for e in f.evidence}
    assert labels["Pitch range vs your average (flatter delivery)"] == 0.4
    assert labels["Pitch range here"] == 1.8
    assert labels["Longest pause between words (at 00:03)"] == 2.4
    assert labels['Phrase "out of 10" said (first at 00:01)'] == 4


def test_delivery_evidence_respects_thresholds_and_categories():
    rep = PhraseRepeat(phrase="out of 10", at=5.0, count=4, first_at=1.0)
    feats = {0: _TF(1.0, 3.0, [rep])}
    f = _flag("slow_hook")  # phrases are not added to hook flags
    _delivery_evidence([f], [_seg(0, 0.0, 10.0)], feats, {0: _av(0.9, 4.0)}, DCFG)
    assert f.evidence == []  # normal pitch range, short pause, no phrase bullet
    s = _flag("silence")
    _delivery_evidence([s], [_seg(0, 0.0, 10.0)], feats, {0: _av(0.1, 0.5)}, DCFG)
    assert s.evidence == []
