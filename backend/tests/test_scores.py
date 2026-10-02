from backend.app.config import load_config
from backend.app.detection.scores import compute_scores
from backend.app.features.text.extract import extract_text_features
from backend.app.segmentation.windows import segment_transcript
from backend.tests.conftest import fixture_transcript
from backend.tests.helpers import HashingEmbedder


def _setup():
    t = fixture_transcript("en")
    segs = segment_transcript(t, load_config("segmentation")["windows"])
    tf = extract_text_features(
        t, segs, HashingEmbedder(), load_config("text_features"), load_config("fillers")
    )
    return segs, tf


def test_scores_script_mode_has_no_visual_or_audio():
    segs, tf = _setup()
    sc = compute_scores(segs, tf, None, load_config("scores"))
    assert len(sc.segments) == len(segs) and not sc.has_video and "internal" in sc.label
    sp = [s for s in sc.segments if s.kind == "speech"]
    assert all(s.visual is None and s.audio is None for s in sc.segments)
    assert all(s.pacing is not None and 0 <= s.pacing <= 100 for s in sp)
    assert all(s.overall is None or 0 <= s.overall <= 100 for s in sc.segments)
    sil = [s for s in sc.segments if s.kind == "silence"]
    assert sil and all(s.pacing is None and s.content is None for s in sil)


def test_repetition_lowers_content():
    segs, tf = _setup()
    cfg = load_config("scores")
    base = compute_scores(segs, tf, None, cfg)
    sp = [f for f in tf.segments if f.kind == "speech" and f.semantic_novelty is not None]
    target = sp[len(sp) // 2]
    for f in tf.segments:
        if f.repetition_similarity is not None:
            f.repetition_similarity = 0.1
    target.repetition_similarity = 0.95
    after = compute_scores(segs, tf, None, cfg)
    b = next(s for s in base.segments if s.index == target.index).content
    a = next(s for s in after.segments if s.index == target.index).content
    assert a < b
