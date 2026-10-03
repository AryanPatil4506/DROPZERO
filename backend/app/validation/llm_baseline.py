"""Plain-LLM baseline ("why not just ask a chatbot?"): give the LLM only the timestamped
transcript and ask where viewers will drop off. Scored exactly like DROPZERO on the same held-out
lectures: each method names its top-k drop points, a point counts if it falls within the tolerance
of a real major drop. The LLM is the same local open-source model the app uses (not ChatGPT: the
project runs open models only); a larger LLM could do better, which the report states.
"""

import json
import re

import numpy as np

_NUM = re.compile(r"\d+(?:\.\d+)?")

PROMPT = (
    "You are an expert in online video audience retention. Below is the timestamped transcript of "
    "a lecture video ({dur} seconds long). Predict the {k} moments where the largest numbers of "
    "viewers will stop watching (ignore the first {skip} seconds, where all videos drop). Reply "
    'with ONLY a JSON object: {{"drop_seconds": [<{k} numbers, seconds from the start>]}}.\n\n'
    "Transcript:\n{transcript}"
)


def transcript_text(rec: dict, max_chars: int) -> str:
    lines = [f"[{int(s)}s] {t}" for s, t in zip(rec["start"], rec["text"], strict=False)]
    out = "\n".join(lines)
    return out[:max_chars]


def parse_seconds(reply: str, k: int, duration: float) -> list[float]:
    m = re.search(r"\{.*\}", reply, re.S)
    vals: list[float] = []
    if m:
        try:
            d = json.loads(m.group(0))
            vals = [float(x) for x in d.get("drop_seconds", []) if isinstance(x, int | float)]
        except (json.JSONDecodeError, TypeError, ValueError):
            vals = []
    if not vals:  # fall back to any numbers in the reply
        vals = [float(x) for x in _NUM.findall(reply)]
    vals = [v for v in vals if 0 <= v <= duration]
    return vals[:k]


def score_points(points: list[float], lec: dict, major: float, tol: float) -> tuple[int, int, int]:
    """(points that hit a real drop, real drops found, real drops total). Non-first segments."""
    act = [i for i in range(1, len(lec["hazard"])) if lec["hazard"][i] >= major]
    s, e = lec["starts"], lec["ends"]

    def hit(t: float, i: int) -> bool:
        return s[i] - tol <= t <= e[i] + tol

    hits = sum(any(hit(t, i) for i in act) for t in points)
    found = sum(any(hit(t, i) for t in points) for i in act)
    return hits, found, len(act)


def top_k_points(scores: np.ndarray, lec: dict, k: int) -> list[float]:
    """Midpoints of the k highest-scoring non-first segments."""
    order = [i for i in np.argsort(-scores) if i != 0][:k]
    return [float((lec["starts"][i] + lec["ends"][i]) / 2) for i in order]
