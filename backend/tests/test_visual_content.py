"""On-screen content: zero-shot labelling, timeline runs, per-segment aggregation and the
picture-speech match, with a fake encoder (fixed vectors); one real-CLIP test marked `model`."""

import numpy as np
import pytest

from backend.app.config import load_config
from backend.app.features.av import add_visual_content, extract_av_features
from backend.app.features.visual.content import (
    classify_frames,
    label_matrix,
    label_runs,
    segment_content,
)
from backend.tests.test_delivery_features import _seg

CFG = load_config("av_features")["content"]
KEYS = [t["key"] for t in CFG["types"]]


def _unit(i, d=16):
    v = np.zeros(d, dtype=np.float32)
    v[i] = 1.0
    return v


class FakeEncoder:
    """Frame value k (all pixels) -> unit vector k; prompts of type j -> unit vector j;
    speech text "topic k" -> unit vector k."""

    def model_id(self):
        return "fake"

    def embed_images(self, frames):
        return np.stack([_unit(int(f[0, 0, 0])) for f in frames])

    def embed_labels(self, texts):
        j = next(i for i, t in enumerate(CFG["types"]) if texts[0] in t["prompts"])
        return np.stack([_unit(j) for _ in texts])

    def embed_speech(self, texts):
        return np.stack([_unit(int(t.split()[-1])) for t in texts])


def _frames(spec):
    """spec: list of (seconds at 1 fps, type index)."""
    return np.concatenate([np.full((n, 4, 4, 3), k, dtype=np.uint8) for n, k in spec])


def test_classify_picks_closest_type_and_marks_unclear():
    labels = label_matrix(FakeEncoder(), CFG["types"])
    img = np.stack([_unit(0), _unit(4), np.full(16, 0.25, dtype=np.float32)])
    img /= np.linalg.norm(img, axis=1, keepdims=True)
    out, conf = classify_frames(img, labels, KEYS, CFG["temperature"], CFG["min_confidence"])
    assert out[:2] == ["slide_text", "talking_head"] and conf[0] > 0.99
    assert out[2] == "unclear"  # equally close to every type


def test_runs_merge_short_glitches():
    labs = ["talking_head"] * 10 + ["slide_text"] + ["talking_head"] * 5 + ["diagram"] * 8
    runs = label_runs(labs, 1.0, 3.0)
    assert [(r.start, r.end, r.label) for r in runs] == [
        (0.0, 16.0, "talking_head"),
        (16.0, 24.0, "diagram"),
    ]
    assert (
        label_runs(["slide_text", "diagram", "diagram", "diagram", "diagram"], 1.0, 3.0)[0].start
        == 0.0
    )


def test_segment_content_dominant_type_and_match():
    labs = ["slide_text"] * 7 + ["diagram"] * 3
    img = np.stack([_unit(0)] * 7 + [_unit(1)] * 3)
    c = segment_content(labs, img, _unit(0), 1.0, 0.0, 10.0)
    assert c.visual_type == "slide_text" and c.visual_type_share == 0.7
    assert c.speech_match == pytest.approx(0.7)
    assert segment_content(labs, img, None, 1.0, 20.0, 30.0).visual_type is None


def test_add_visual_content_end_to_end_with_fake_encoder():
    segs = [_seg(0, 0.0, 10.0), _seg(1, 10.0, 20.0), _seg(2, 20.0, 30.0)]
    segs = [
        s.model_copy(update={"text": f"topic {k}"}) for s, k in zip(segs, (4, 1, 6), strict=True)
    ]
    base = extract_av_features(
        "p", segs, np.zeros(16000 * 30), np.zeros(0), [], True, load_config("av_features")
    )
    rgb = _frames([(10, 4), (10, 1), (10, 4)])  # talking head, diagram, talking head
    fs = add_visual_content(base, segs, rgb, FakeEncoder(), CFG)
    assert [s.visual_type for s in fs.segments] == ["talking_head", "diagram", "talking_head"]
    # picture matches speech in segments 0 and 1, not in 2 (talks about topic 6)
    assert [s.speech_match for s in fs.segments] == [1.0, 1.0, 0.0]
    assert fs.segments[2].speech_match_ratio == 0.0
    assert [(r.start, r.end, r.type) for r in fs.visual_timeline] == [
        (0.0, 10.0, "talking_head"),
        (10.0, 20.0, "diagram"),
        (20.0, 30.0, "talking_head"),
    ]
    assert fs.visual_types["diagram"] == "Diagram" and fs.visual_model == "fake"
    again = add_visual_content(base, segs, rgb, FakeEncoder(), CFG)
    assert again == fs  # deterministic


def test_no_frames_leaves_features_unchanged():
    segs = [_seg(0, 0.0, 10.0)]
    base = extract_av_features(
        "p", segs, np.zeros(16000 * 10), np.zeros(0), [], True, load_config("av_features")
    )
    empty = np.zeros((0, 4, 4, 3), dtype=np.uint8)
    assert add_visual_content(base, segs, empty, FakeEncoder(), CFG) == base


@pytest.mark.model
def test_real_clip_tells_slide_from_blank():
    from PIL import Image, ImageDraw

    from backend.app.features.visual.content import ClipEncoder

    slide = Image.new("RGB", (224, 224), "white")
    d = ImageDraw.Draw(slide)
    for i in range(8):
        d.text((12, 12 + i * 24), "• System calls move into the kernel", fill="black")
    blank = Image.new("RGB", (224, 224), "black")
    enc = ClipEncoder(CFG)
    img = enc.embed_images(np.stack([np.asarray(slide), np.asarray(blank)]))
    out, _ = classify_frames(
        img, label_matrix(enc, CFG["types"]), KEYS, CFG["temperature"], CFG["min_confidence"]
    )
    assert out[0] in {"slide_text", "screen"} and out[1] == "blank"
