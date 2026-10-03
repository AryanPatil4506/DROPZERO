"""Rewrite suggestions for weak sections: the local LLM tightens the flagged lines.

The model only rewrites text the creator already wrote. Deterministic checks decide whether a
rewrite is shown:
- no numbers that are not already in the original lines (no invented facts or statistics);
- meaningfully shorter (at most `max_ratio` of the original word count);
- same script as the video (Devanagari for Hindi, Roman script for Hinglish / English);
- same meaning: LaBSE similarity to the original of at least `min_similarity` (catches garbled or
  meaning-losing rewrites, which the small model produces most often in Hindi).
A rewrite that fails twice is not shown; the response says why (source="none").
The time saving is an estimate from this video's own speaking rate and is labelled as such.
"""

import json
import re

from pydantic import BaseModel

from backend.app.detection.flags import mmss
from backend.app.explain.llm import LANG_NAMES, LocalLLM, check_numbers
from backend.app.features.text.embedder import Embedder
from backend.app.schemas.flags import Flag
from backend.app.schemas.transcript import Transcript

# Bump when the checks or prompt change, so cached rewrites made under older rules are redone.
REWRITE_VERSION = "rewrite-2"

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_NUM = re.compile(r"\d+(?:[.:]\d+)?%?")

SYSTEM = (
    "You are a script editor for a video creator. Rewrite the given lines so they say the same "
    "thing in fewer words: cut filler, repetition and throat-clearing, keep the speaker's voice "
    "and any technical terms. The lines will be spoken aloud, so use natural, complete sentences, "
    "not notes. Rules: write in {lang}; do not add facts, numbers, names or claims that are not "
    "in the original; do not use more than {max_words} words. Reply with ONLY a JSON object: "
    '{"rewrite": "<the new lines>", "what_changed": "<one short sentence>"}.'
)


class Rewrite(BaseModel):
    flag_id: str
    start: float
    end: float
    source: str  # "llm" | "none"
    model: str | None
    original: str
    rewrite: str | None
    what_changed: str | None = None
    original_words: int
    rewrite_words: int | None = None
    meaning_similarity: float | None = None  # LaBSE cosine, original vs rewrite
    est_seconds_saved: float | None = None  # from this video's speaking rate; an estimate
    rejected: list[str] = []  # why attempts were refused


def original_lines(flag: Flag, t: Transcript, max_chars: int) -> tuple[str, float, float]:
    """Whole sentences overlapping the flag, so the rewrite has complete thoughts."""
    sents = [s for s in t.sentences if s.start < flag.end and s.end > flag.start]
    if not sents:
        return "", flag.start, flag.end
    text = " ".join(s.text.strip() for s in sents)
    return text[:max_chars], sents[0].start, sents[-1].end


def _words(text: str) -> int:
    return len(text.split())


def script_ok(text: str, language: str) -> bool:
    deva = len(_DEVANAGARI.findall(text))
    letters = sum(ch.isalpha() for ch in text) or 1
    if language == "hi":
        return deva / letters > 0.5
    return deva / letters < 0.1  # English and Roman-script Hinglish


def _parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("rewrite"), str) or not d["rewrite"].strip():
        return None
    return d


def rewrite_flag(
    llm: LocalLLM,
    flag: Flag,
    t: Transcript,
    language: str,
    words_per_second: float,
    cfg: dict,
    embedder: Embedder | None = None,
) -> Rewrite:
    original, start, end = original_lines(flag, t, cfg["max_chars"])
    n = _words(original)
    base = dict(flag_id=flag.id, start=start, end=end, original=original, original_words=n)
    if n < cfg["min_words"]:
        return Rewrite(
            **base, source="none", model=None, rewrite=None, rejected=["too little text to rewrite"]
        )
    max_words = max(cfg["min_words"] // 2, int(n * cfg["max_ratio"]))
    min_words = max(1, int(n * cfg["min_ratio"]))
    allowed = set(_NUM.findall(original)) | {x.rstrip("%") for x in _NUM.findall(original)}
    system = SYSTEM.replace("{lang}", LANG_NAMES.get(language, "English")).replace(
        "{max_words}", str(max_words)
    )
    user = f"Lines ({mmss(start)}–{mmss(end)}, {n} words):\n{original}"
    rejected: list[str] = []
    for attempt in range(cfg["retries"] + 1):
        if attempt:
            user += "\n\nYour previous rewrite was refused: " + "; ".join(rejected) + ". Try again."
        d = _parse(llm.chat(system, user))
        rejected = []
        if d is None:
            rejected.append("invalid JSON")
            continue
        text = d["rewrite"].strip()
        k = _words(text)
        if k > max_words:
            rejected.append(f"not shorter enough ({k} words, limit {max_words})")
        if k < min_words:
            rejected.append(f"cut too much ({k} words, at least {min_words})")
        if bad := check_numbers(text, allowed):
            rejected.append("added numbers not in the original: " + ", ".join(bad))
        if not script_ok(text, language):
            rejected.append("wrong script for the video's language")
        sim = None
        if not rejected and embedder is not None:
            v = embedder.embed([original, text])
            sim = round(float(v[0] @ v[1]), 3)
            if sim < cfg["min_similarity"]:
                rejected.append(
                    f"meaning changed (similarity {sim}, needs {cfg['min_similarity']})"
                )
        if not rejected:
            saved = (n - k) / words_per_second if words_per_second > 0 else None
            return Rewrite(
                **base,
                source="llm",
                model=llm.name,
                rewrite=text,
                what_changed=(
                    d.get("what_changed") if isinstance(d.get("what_changed"), str) else None
                ),
                rewrite_words=k,
                meaning_similarity=sim,
                est_seconds_saved=round(saved, 1) if saved is not None else None,
            )
    return Rewrite(**base, source="none", model=llm.name, rewrite=None, rejected=rejected)
