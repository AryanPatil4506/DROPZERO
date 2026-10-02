import json

from backend.app.config import load_config
from backend.app.explain.llm import allowed_numbers, check_numbers, evidence_object, explain_flag
from backend.app.schemas.flags import Edit, Evidence, Flag
from backend.tests.conftest import fixture_transcript


def _flag():
    return Flag(
        id="f1",
        start=113.0,
        end=127.2,
        severity="high",
        category="repetition",
        source="rule",
        risk_score=0.7,
        title="Repeats 00:49–01:03",
        explanation="This section repeats.",
        evidence=[
            Evidence(
                label="Similarity to earlier section", value=0.7342, ref_start=49.0, ref_end=63.0
            )
        ],
        edit_ids=["e1"],
    )


EDITS = [
    Edit(
        id="e1",
        flag_id="f1",
        action="CUT",
        start=113.0,
        end=127.0,
        reason="Cut 01:53–02:07: repeats 00:49–01:03",
        simulatable=True,
    )
]


class FakeLLM:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, system, user):
        self.calls += 1
        return self.replies.pop(0)


def test_number_guard():
    ev = evidence_object(_flag(), EDITS, fixture_transcript("en"), load_config("llm"))
    allowed = allowed_numbers(ev)
    assert check_numbers("Similarity 0.73 to 00:49–01:03; cut 01:53–02:07", allowed) == []
    assert check_numbers("73% of viewers", allowed) == []  # ratio phrased as a percentage
    assert check_numbers("42% of viewers leave at 03:10", allowed) == ["42%", "03:10"]


def test_valid_llm_answer_is_used():
    good = json.dumps(
        {
            "reason": "Repeats 00:49–01:03.",
            "why_viewers_leave": "Similarity 0.73.",
            "fix": "Cut 01:53–02:07.",
            "rewrite": None,
        }
    )
    llm = FakeLLM([good])
    out = explain_flag(llm, _flag(), EDITS, fixture_transcript("en"), "en", load_config("llm"))
    assert out.source == "llm" and out.model == "fake" and llm.calls == 1


def test_invented_numbers_fall_back_to_template():
    bad = json.dumps(
        {
            "reason": "x",
            "why_viewers_leave": "40% of viewers leave here.",
            "fix": "Cut it.",
            "rewrite": None,
        }
    )
    llm = FakeLLM([bad, bad])
    out = explain_flag(llm, _flag(), EDITS, fixture_transcript("en"), "en", load_config("llm"))
    assert out.source == "template" and out.rejected == ["40%"] and llm.calls == 2
    assert out.fix.startswith("Cut 01:53–02:07")


def test_list_values_are_joined():
    reply = json.dumps(
        {
            "reason": "Repeats 00:49–01:03.",
            "why_viewers_leave": ["One.", "Two."],
            "fix": "Cut 01:53–02:07.",
            "rewrite": None,
        }
    )
    out = explain_flag(
        FakeLLM([reply]), _flag(), EDITS, fixture_transcript("en"), "en", load_config("llm")
    )
    assert out.source == "llm" and out.why_viewers_leave == "One. Two."
