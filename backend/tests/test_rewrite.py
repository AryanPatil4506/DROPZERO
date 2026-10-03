import json

from backend.app.config import load_config
from backend.app.explain.rewrite import original_lines, rewrite_flag, script_ok
from backend.app.schemas.flags import Flag
from backend.tests.conftest import fixture_transcript
from backend.tests.test_explain import FakeLLM

CFG = load_config("llm")["rewrite"]


def _flag(start=113.0, end=127.2):
    return Flag(
        id="f1",
        start=start,
        end=end,
        severity="high",
        category="repetition",
        source="rule",
        risk_score=0.7,
        title="Repeats 00:49–01:03",
        explanation="This section repeats.",
        evidence=[],
        edit_ids=[],
    )


def _reply(text):
    return json.dumps({"rewrite": text, "what_changed": "Shorter."})


def test_original_lines_are_whole_sentences():
    t = fixture_transcript("en")
    text, start, end = original_lines(_flag(), t, 900)
    assert text and start <= 113.0 and end >= 127.2
    assert text.split()[0][0].isupper()


def test_good_rewrite_is_accepted_with_estimated_saving():
    t = fixture_transcript("en")
    original, _, _ = original_lines(_flag(), t, 900)
    k = int(len(original.split()) * 0.6)
    short = " ".join(original.split()[:k])
    llm = FakeLLM([_reply(short)])
    out = rewrite_flag(llm, _flag(), t, "en", 2.5, CFG)
    assert out.source == "llm" and out.rewrite == short and out.rewrite_words == k
    assert out.est_seconds_saved == round((out.original_words - k) / 2.5, 1)
    assert llm.calls == 1


def test_longer_or_invented_numbers_are_refused_then_retried():
    t = fixture_transcript("en")
    original, _, _ = original_lines(_flag(), t, 900)
    too_long = original + " and more words here"
    llm = FakeLLM([_reply(too_long), _reply("Agents call 47 tools in 3 minutes flat.")])
    out = rewrite_flag(llm, _flag(), t, "en", 2.5, CFG)
    assert out.source == "none" and out.rewrite is None
    assert any("47" in r for r in out.rejected)  # second attempt invented a number
    assert llm.calls == 2


def test_wrong_script_is_refused():
    assert script_ok("आज हम दही जमाएंगे", "hi") and not script_ok("aaj hum dahi jamayenge", "hi")
    assert script_ok("aaj hum phone dekhenge", "hinglish") and not script_ok(
        "आज हम फोन", "hinglish"
    )
    t = fixture_transcript("hi")
    flag = _flag(0.0, 30.0)
    llm = FakeLLM([_reply("Today we make thick curd at home."), _reply("Still English, sorry.")])
    out = rewrite_flag(llm, flag, t, "hi", 2.0, CFG)
    assert out.source == "none" and "wrong script" in " ".join(out.rejected)


class FakeEmbedder:
    """Identical text -> similarity 1; anything else -> the given value."""

    def __init__(self, sim):
        self.sim = sim

    def embed(self, texts):
        import numpy as np

        a = np.array([1.0, 0.0])
        b = np.array([self.sim, (1 - self.sim**2) ** 0.5])
        return np.stack([a, b])


def test_meaning_check_refuses_drift_and_reports_similarity():
    t = fixture_transcript("en")
    original, _, _ = original_lines(_flag(), t, 900)
    short = " ".join(original.split()[: int(len(original.split()) * 0.6)])
    out = rewrite_flag(FakeLLM([_reply(short)]), _flag(), t, "en", 2.5, CFG, FakeEmbedder(0.9))
    assert out.source == "llm" and out.meaning_similarity == 0.9
    out = rewrite_flag(
        FakeLLM([_reply(short), _reply(short)]), _flag(), t, "en", 2.5, CFG, FakeEmbedder(0.5)
    )
    assert out.source == "none" and "meaning changed" in " ".join(out.rejected)


def test_over_compressed_rewrite_is_refused():
    t = fixture_transcript("en")
    llm = FakeLLM([_reply("Agents loop."), _reply("Agents loop.")])
    out = rewrite_flag(llm, _flag(), t, "en", 2.5, CFG)
    assert out.source == "none" and "cut too much" in " ".join(out.rejected)


def test_too_little_text_is_not_sent_to_the_model():
    t = fixture_transcript("en")
    llm = FakeLLM([])
    out = rewrite_flag(llm, _flag(0.0, 0.5), t, "en", 2.5, CFG)
    assert out.source == "none" and llm.calls == 0


def test_script_check_follows_code_mixed_original():
    from backend.app.explain.rewrite import script_ok

    mixed = "Hello friends, welcome. The topic is System Call. Last video में हमने देखा था"
    assert script_ok(mixed, "hi", original=mixed)  # the creator's own mix always passes
    assert not script_ok(mixed, "hi")  # the old fixed rule refused it
    assert not script_ok(
        "यह पूरी तरह से हिंदी में लिखा गया वाक्य है", "hi", original="All English here."
    )
