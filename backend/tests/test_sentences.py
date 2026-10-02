from backend.app.features.text.lexical import tokens
from backend.app.schemas.transcript import Word
from backend.app.segmentation.sentences import build_sentences
from backend.tests.conftest import fixture_transcript


def _words(spec):
    """spec: list of (text, start, end)"""
    return [Word(text=t, start=s, end=e) for t, s, e in spec]


def test_english_punctuation_and_abbreviations(seg_cfg):
    cfg = seg_cfg["sentences"]
    w = _words(
        [
            ("Ask", 0, 0.3),
            ("Dr.", 0.35, 0.6),
            ("Rao.", 0.65, 1),
            ("Why?", 1.1, 1.4),
            ("Yes!", 1.5, 1.8),
            ("ok", 1.9, 2.1),
        ]
    )
    s = build_sentences(w, cfg)
    assert [x.text for x in s] == ["Ask Dr. Rao.", "Why?", "Yes!", "ok"]
    assert [x.end_reason for x in s] == ["punct", "punct", "punct", "end"]


def test_hindi_danda(seg_cfg):
    t = fixture_transcript("hi")
    assert all(s.text.endswith(("।", "?")) for s in t.sentences[:-1] if s.end_reason == "punct")
    assert sum(s.end_reason == "punct" for s in t.sentences) >= 20
    # Devanagari words with matras/virama are not split apart
    assert tokens("क्या आपको दही पसंद है?") == ["क्या", "आपको", "दही", "पसंद", "है"]


def test_hinglish_pause_fallback(seg_cfg):
    t = fixture_transcript("hinglish")
    pause = [s for s in t.sentences if s.end_reason == "pause"]
    assert pause, "unpunctuated stretch should be split at pauses"
    cfg = seg_cfg["sentences"]
    assert all(s.end - s.start >= cfg["pause_min_sentence_s"] for s in pause)


def test_silence_gap_always_splits(seg_cfg):
    cfg = seg_cfg["sentences"]
    w = _words([("hello", 0, 0.4), ("there", 3.0, 3.4), ("friend", 3.5, 3.8)])
    s = build_sentences(w, cfg)
    assert [x.end_reason for x in s] == ["silence", "end"]


def test_sentences_cover_all_words(lang):
    t = fixture_transcript(lang)
    assert t.sentences[0].word_start == 0 and t.sentences[-1].word_end == len(t.words)
    for a, b in zip(t.sentences, t.sentences[1:], strict=False):
        assert a.word_end == b.word_start


def test_whisper_phrase_breaks_split_unpunctuated_speech(seg_cfg):
    cfg = seg_cfg["sentences"]
    w = [Word(text=f"w{i}", start=i * 0.4, end=i * 0.4 + 0.35) for i in range(20)]
    w[7] = w[7].model_copy(update={"phrase_break": True})  # ends at 3.15 s
    w[9] = w[9].model_copy(update={"phrase_break": True})  # too soon after the last split
    s = build_sentences(w, cfg)
    assert [x.end_reason for x in s] == ["phrase", "end"]
    assert s[0].word_end == 8


def test_max_sentence_length(seg_cfg):
    cfg = seg_cfg["sentences"]
    w = [Word(text=f"w{i}", start=i * 0.4, end=i * 0.4 + 0.35) for i in range(100)]  # 40 s
    s = build_sentences(w, cfg)
    assert all(x.end - x.start <= cfg["max_sentence_s"] + 0.5 for x in s)
    assert s[0].end_reason == "max_length"
