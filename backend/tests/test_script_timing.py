from backend.app.schemas.project import Language
from backend.app.schemas.transcript import TimingSource
from backend.app.segmentation.windows import segment_transcript
from backend.app.transcription.script_timing import estimate_transcript, parse_script
from backend.tests.helpers import FIX


def test_parse_markdown():
    md = """# Title here

Intro line with a [link](http://x.y) and **bold**.
- first point
- second point

```python
print("not spoken")
```
1. numbered item
दही जमाना आसान है ।
"""
    paras = parse_script(md)
    flat = [" ".join(p) for p in paras]
    assert flat[0] == "Title here"
    assert flat[1] == "Intro line with a link and bold."
    assert flat[2:4] == ["first point", "second point"]
    assert "print" not in " ".join(flat)
    assert flat[4] == "numbered item"
    assert flat[5] == "दही जमाना आसान है।"  # detached danda joins the previous word


def test_estimated_timing(lang, seg_cfg):
    text = (FIX / f"{lang}_script.txt").read_text(encoding="utf-8")
    run = lambda: estimate_transcript(  # noqa: E731
        text, "p", Language(lang), seg_cfg["script_timing"], seg_cfg["sentences"]
    )
    t = run()
    assert t.timing_source == TimingSource.ESTIMATED
    assert t.asr_model is None
    starts = [w.start for w in t.words]
    assert starts == sorted(starts) and all(w.end > w.start for w in t.words)
    assert t.duration_s > 60
    assert run().model_dump() == t.model_dump()
    segs = segment_transcript(t, seg_cfg["windows"])
    assert all(s.timing_source == TimingSource.ESTIMATED for s in segs)
    assert segs[-1].end == t.duration_s


def test_rate_depends_on_language(seg_cfg):
    cfg = seg_cfg["script_timing"]
    text = "one two three four five six seven eight nine ten."
    en = estimate_transcript(text, "p", Language.EN, cfg, seg_cfg["sentences"])
    hi = estimate_transcript(text, "p", Language.HI, cfg, seg_cfg["sentences"])
    assert hi.duration_s > en.duration_s  # slower configured rate for Hindi
