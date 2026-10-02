import numpy as np

from backend.app.config import load_config
from backend.app.detection.promises import _strip_cues, build_ledger
from backend.app.schemas.flags import PromiseCheck
from backend.tests.conftest import fixture_transcript


class StubEmbedder:
    """Texts mentioning the reservation point one way, everything else another."""

    def model_id(self):
        return "stub"

    def embed(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            v = (
                np.array([1.0, 0.0])
                if ("reservation" in low or "book a table" in low)
                else np.array([0.0, 1.0])
            )
            out.append(v)
        return np.array(out)


def _title(first=None):
    return PromiseCheck(
        title="I Built an AI Agent in 24 Hours",
        first_mention_s=first,
        first_mention_text=None,
        best_match_s=None,
        best_similarity=None,
    )


def test_strip_cues():
    cues = ["by the end", "you will see"]
    text = "By the end of this video you will see the agent book a table."
    assert _strip_cues(text, cues) == "the agent book a table"
    assert _strip_cues("You will see it.", cues) == "You will see it."  # too short: keep all


def test_intro_promise_paid_off_late():
    t = fixture_transcript("en")
    led = build_ledger(t, _title(40.0), StubEmbedder(), load_config("promises"))
    assert led[0].source == "title" and led[0].status == "kept"
    intro = [p for p in led if p.source == "intro"]
    booking = next(p for p in intro if "reservation" in p.text)
    assert booking.payoff_text and "book a table" in booking.payoff_text
    assert booking.payoff_at > booking.made_at + 60 and booking.status == "late"


def test_open_promise_when_nothing_matches():
    class Orthogonal(StubEmbedder):
        def embed(self, texts):
            n = len(texts)
            return np.eye(n)

    t = fixture_transcript("en")
    led = build_ledger(t, _title(None), Orthogonal(), load_config("promises"))
    assert led[0].status == "open"
    assert all(p.status == "open" for p in led if p.source == "intro")
