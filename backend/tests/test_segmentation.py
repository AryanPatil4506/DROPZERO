from backend.app.schemas.project import Language
from backend.app.schemas.transcript import TimingSource, Transcript, Word
from backend.app.segmentation.sentences import build_sentences
from backend.app.segmentation.windows import segment_transcript
from backend.tests.conftest import fixture_transcript


def _tiles(segs, duration):
    assert segs[0].start == 0.0
    assert segs[-1].end == round(duration, 3)
    for a, b in zip(segs, segs[1:], strict=False):
        assert a.end == b.start, (a.index, a.end, b.start)
        assert a.end > a.start


def _exceptions(segs, cfg):
    """Segments outside [min_s, max_s] must be one of the documented exceptions."""
    lo, hi, sil = cfg["min_s"], cfg["max_s"], cfg["silence_segment_min_s"]
    out = []
    for i, s in enumerate(segs):
        d = s.end - s.start
        if lo - 1e-6 <= d <= hi + 1e-6:
            continue
        prev_sil = i > 0 and segs[i - 1].kind == "silence"
        next_sil = i + 1 < len(segs) and segs[i + 1].kind == "silence"
        if s.kind == "speech" and d < lo and (prev_sil or i == 0) and (next_sil or s is segs[-1]):
            out.append(("short_run_between_silences", s.index))
        elif s.kind == "speech" and s is segs[-1] and d <= hi + sil:
            out.append(("absorbs_trailing_silence", s.index))
        elif s.kind == "speech" and d > hi and len(s.sentence_ids) == 1 and d <= hi + sil:
            out.append(("single_sentence_piece_with_gaps", s.index))
        else:
            raise AssertionError(f"undocumented length {d:.2f}s at segment {s.index}")
    return out


def test_tiling_and_lengths(lang, seg_cfg):
    t = fixture_transcript(lang)
    segs = segment_transcript(t, seg_cfg["windows"])
    _tiles(segs, t.duration_s)
    _exceptions(segs, seg_cfg["windows"])
    # every word is in exactly one speech segment
    covered = [i for s in segs for i in range(s.word_start, s.word_end)]
    assert covered == list(range(len(t.words)))


def test_deterministic_and_stable_ids(lang, seg_cfg):
    t = fixture_transcript(lang)
    a = segment_transcript(t, seg_cfg["windows"])
    b = segment_transcript(fixture_transcript(lang), seg_cfg["windows"])
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]
    assert [s.id for s in a] == [f"p-{lang}:{i:04d}" for i in range(len(a))]


def test_boundaries_prefer_sentence_ends(lang, seg_cfg):
    segs = segment_transcript(fixture_transcript(lang), seg_cfg["windows"])
    speech = [s for s in segs if s.kind == "speech" and s.boundary != "end"]
    clean = sum(s.boundary in ("sentence", "pause") for s in speech)
    assert clean / len(speech) >= 0.8


def test_english_silent_intro_is_own_segment(seg_cfg):
    t = fixture_transcript("en")
    segs = segment_transcript(t, seg_cfg["windows"])
    intro = [s for s in segs if s.kind == "silence" and s.end <= t.words[0].start + 1e-6]
    assert intro and intro[0].start == 0.0
    assert intro[-1].end == t.words[0].start  # "intro runs 18 s before the first word"
    assert segs[len(intro)].kind == "speech"


def test_hindi_internal_silence(seg_cfg):
    segs = segment_transcript(fixture_transcript("hi"), seg_cfg["windows"])
    sil = [s for s in segs if s.kind == "silence"]
    assert len(sil) == 1 and sil[0].end - sil[0].start >= 7.0
    assert sil[0].text == "" and sil[0].word_start == sil[0].word_end


def test_long_sentence_forced_split(seg_cfg):
    words = [Word(text=f"w{i}", start=i * 0.5, end=i * 0.5 + 0.4) for i in range(80)]
    words[39] = Word(text="w39", start=19.5, end=19.9)
    words[40:] = [Word(text=w.text, start=w.start + 0.6, end=w.end + 0.6) for w in words[40:]]
    t = Transcript(
        project_id="p",
        language_declared=Language.EN,
        timing_source=TimingSource.ASR,
        duration_s=41.0,
        words=words,
        sentences=build_sentences(
            words, {**seg_cfg["sentences"], "pause_gap_s": 99, "max_sentence_s": 99}
        ),
        transcript_schema_version="t",
    )
    assert len(t.sentences) == 1  # one 40 s run-on "sentence"
    segs = segment_transcript(t, seg_cfg["windows"])
    _tiles(segs, 41.0)
    assert all(s.end - s.start <= seg_cfg["windows"]["max_s"] + 0.5 for s in segs)
    assert any(s.boundary == "forced_split" for s in segs)


def test_no_speech_is_all_silence(seg_cfg):
    t = Transcript(
        project_id="p",
        language_declared=Language.EN,
        timing_source=TimingSource.ASR,
        duration_s=70.0,
        words=[],
        sentences=[],
        transcript_schema_version="t",
    )
    segs = segment_transcript(t, seg_cfg["windows"])
    _tiles(segs, 70.0)
    assert all(s.kind == "silence" for s in segs)
    assert all(s.end - s.start <= seg_cfg["windows"]["max_s"] + 1e-6 for s in segs)


def test_boundary_hints_pull_boundaries(seg_cfg):
    t = fixture_transcript("en")
    base = segment_transcript(t, seg_cfg["windows"])
    # put a hint on a sentence end that is not currently a boundary
    ends = {round(s.end, 3) for s in base}
    candidates = [s for s in t.sentences[3:] if round(s.end, 3) not in ends]
    target = candidates[0]
    hinted = segment_transcript(t, seg_cfg["windows"], boundary_hints=[target.end])
    _tiles(hinted, t.duration_s)
    assert any(abs(s.end - target.end) <= seg_cfg["windows"]["hint_tolerance_s"] for s in hinted)
