import copy

import numpy as np
import pytest

from backend.app.config import load_config
from backend.app.features.text import semantic
from backend.app.features.text.extract import extract_text_features
from backend.app.features.text.lexical import (
    Lexicon,
    find_fillers,
    has_number_claim,
    is_question,
    tokens,
)
from backend.app.segmentation.windows import segment_transcript
from backend.app.transcription.script_timing import parse_script
from backend.tests.conftest import fixture_transcript
from backend.tests.helpers import FIX, HashingEmbedder


@pytest.fixture
def lex():
    return Lexicon.from_config(load_config("fillers"), load_config("text_features"))


# ---------- lexical


@pytest.mark.parametrize(
    "text,expected",
    [
        ("So, um, you know, it basically works.", ["so", "um", "you know", "basically"]),
        ("I said so many times.", []),  # "so" only counts sentence-initially
        ("Toh matlab yaar ye kaam karta hai", ["toh", "matlab", "yaar"]),
        ("agar dhoop hai toh photo achhi aati hai", []),
        ("तो मतलब ये है ना", ["तो", "मतलब", "है ना"]),
    ],
)
def test_fillers(lex, text, expected):
    assert find_fillers(tokens(text), lex) == expected


@pytest.mark.parametrize(
    "text,q",
    [
        ("Why was it failing?", True),
        ("This works.", False),
        ("kya ye phone 4K record karta hai", True),  # unpunctuated Hinglish
        ("ye phone achha hai na", True),  # tag question
        ("दही कितनी देर में जमता है?", True),
        ("दही जम गया।", False),
    ],
)
def test_questions(lex, text, q):
    assert is_question(text, lex) is q


def test_number_claims(lex):
    assert has_number_claim("It failed 7 out of 10 times.", lex)
    assert has_number_claim("सिर्फ आठ घंटे में", lex)
    assert not has_number_claim("एक बात समझिए", lex)  # एक usually means "a"
    assert has_number_claim("teen phones liye", lex)
    assert not has_number_claim("one of the best", lex)


# ---------- semantic (hand-built unit vectors)


def _e(*rows):
    m = np.array(rows, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def test_segment_repetition_respects_min_gap():
    emb = _e([1, 0, 0], [1, 0.05, 0], [0, 1, 0], [1, 0.02, 0])
    starts, ends = [0, 10, 20, 40], [10, 20, 30, 50]
    rep = semantic.segment_repetition(emb, starts, ends, min_gap_s=20, threshold=0.95)
    assert rep[1].similarity is None  # item 0 ended only 0 s before
    assert rep[3].match == 0 and rep[3].similarity > 0.99
    assert rep[3].count == 2  # items 0 and 1 both ended >= 20 s before and are similar


def test_novelty_and_information_gain():
    emb = _e([1, 0], [1, 0], [0, 1])
    nov = semantic.novelty(emb)
    assert nov[0] is None and nov[1] == pytest.approx(0, abs=1e-6)
    assert nov[2] == pytest.approx(1, abs=1e-6)
    gain = semantic.information_gain(emb, [0, 10, 20], [10, 20, 30], window_s=15)
    assert gain[2] == pytest.approx(1, abs=1e-6)  # only item 1 is in the window


def test_topic_boundary_found_at_switch():
    a, b = [1, 0, 0], [0, 1, 0]
    emb = _e(a, a, [1, 0.1, 0], a, b, b, [0, 1, 0.1], b)
    starts = [i * 12.0 for i in range(8)]
    assert semantic.topic_boundaries(emb, starts, 2, 0.5, 0.02, 30.0) == [4]


# ---------- extractor on fixtures


def _features(lang, cfg=None, embedder=None):
    t = fixture_transcript(lang)
    segs = segment_transcript(t, load_config("segmentation")["windows"])
    cfg = cfg or load_config("text_features")
    return (
        t,
        segs,
        extract_text_features(t, segs, embedder or HashingEmbedder(), cfg, load_config("fillers")),
    )


def test_extractor_shape_and_determinism(lang):
    t, segs, fs = _features(lang)
    assert [f.segment_id for f in fs.segments] == [s.id for s in segs]
    assert fs.feature_schema_version and fs.embedding_model == "test/hashing-bow-256"
    assert sum(f.word_count for f in fs.segments) == len(t.words)
    assert fs.baseline_words_per_second > 0
    speech_pace = [f.pace_ratio for f in fs.segments if f.kind == "speech"]
    assert all(p is not None and p > 0 for p in speech_pace)
    assert fs.topics[0].start == 0 and fs.topics[-1].end == segs[-1].end
    assert _features(lang)[2].model_dump() == fs.model_dump()


def test_silence_segments_have_no_semantics():
    _, _, fs = _features("en")
    sil = [f for f in fs.segments if f.kind == "silence"]
    assert sil and all(
        f.word_count == 0 and f.semantic_novelty is None and f.repetition_similarity is None
        for f in sil
    )


def test_lexical_counts_per_language(lang):
    _, _, fs = _features(lang)
    fillers = [x for f in fs.segments for x in f.fillers]
    assert sum(f.question_count for f in fs.segments) >= 1
    assert sum(f.claim_count for f in fs.segments) >= 1
    expected = {
        "en": {"um", "you know", "basically"},
        "hi": {"मतलब", "तो"},
        "hinglish": {"basically", "matlab", "yaar"},
    }[lang]
    assert expected <= set(fillers)


@pytest.mark.parametrize(
    "lang,repeat_marker,original_marker",
    [
        ("en", "Basically, an agent is just", "So what is an AI agent?"),
        ("hi", "एक बात फिर से", "सबसे पहले दूध"),
        ("hinglish", "Yaar dekho daylight", "Pehle baat karte hain daylight"),
    ],
)
def test_planted_repetition_is_matched(lang, repeat_marker, original_marker):
    """The lexical test embedder can't judge paraphrase quality, so the threshold is lowered here;
    the real-model version of this test is test_real_model_finds_planted_repetition."""
    cfg = copy.deepcopy(load_config("text_features"))
    cfg["repetition"]["sentence_threshold"] = 0.45
    t, segs, fs = _features(lang, cfg)
    rep_seg = next(
        s
        for s in segs
        if repeat_marker.split()[0] in s.text and " ".join(repeat_marker.split()[1:3]) in s.text
    )
    orig_seg = next(
        s
        for s in segs
        if original_marker.split()[0] in s.text and " ".join(original_marker.split()[1:3]) in s.text
    )
    f = fs.segments[rep_seg.index]
    assert f.repetition_matches, "planted repeat not matched"
    m = f.repetition_matches[0]
    assert orig_seg.start - 1 <= m.matched_start <= orig_seg.end + 15
    assert m.start - m.matched_end >= cfg["repetition"]["min_gap_s"]


@pytest.mark.model
@pytest.mark.parametrize(
    "lang,repeat_marker",
    [
        ("en", "Basically, an agent"),
        ("hi", "अच्छा, एक बात फिर"),
        ("hinglish", "Yaar dekho daylight"),
    ],
)
def test_real_model_finds_planted_repetition(lang, repeat_marker):
    from backend.app.features.text.embedder import SentenceTransformerEmbedder

    cfg = load_config("text_features")
    emb = SentenceTransformerEmbedder(cfg["embedding"], "auto")
    t, segs, fs = _features(lang, embedder=emb)
    # the planted repeat is a whole paragraph; unpunctuated (Hinglish) it can straddle segments
    first = next(s for s in segs if repeat_marker in s.text)
    w0 = first.word_start + first.text.split().index(repeat_marker.split()[0])
    # fixture words map 1:1 to the script's tokens (see scripts/make_asr_fixtures.py)
    paras = parse_script((FIX / f"{lang}_script.txt").read_text(encoding="utf-8"))
    para = next(p for p in paras if " ".join(p).startswith(repeat_marker))
    para_end = t.words[w0 + len(para) - 1].end
    start = t.words[w0].start
    covering = {
        s.index for s in segs if s.kind == "speech" and s.start < para_end and s.end > start
    }
    assert any(fs.segments[i].repetition_matches for i in covering), f"{lang}: not detected"
    # segment-level ranking: the most repetitive segment of the video is part of the repeat.
    # (Sentence-level matches also fire on some non-repeats in hi/hinglish at the provisional
    # threshold; see docs/build-status.md. That is why this asserts ranking, not a clean flag set.)
    top = max(
        (x for x in fs.segments if x.repetition_similarity is not None),
        key=lambda x: x.repetition_similarity,
    )
    assert top.index in covering
    assert _features(lang, embedder=emb)[2].model_dump() == fs.model_dump()
