"""Script-only mode: estimate word timing from a per-language speaking rate.

Every transcript produced here has timing_source="estimated", and that label is carried to every
segment and shown in the UI. Deterministic: no randomness, durations depend only on word order.
"""

import re
from typing import Any

from backend.app.schemas.project import Language
from backend.app.schemas.transcript import TimingSource, Transcript, Word
from backend.app.segmentation.sentences import build_sentences, is_terminal
from backend.app.versions import TRANSCRIPT_SCHEMA_VERSION

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s*")
_EMPH = re.compile(r"(\*\*|__|\*|`)")
_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)


def parse_script(text: str) -> list[list[str]]:
    """TXT/MD -> paragraphs of spoken tokens. Headings and list items are their own paragraphs;
    fenced code blocks are skipped (not spoken)."""
    paragraphs: list[list[str]] = []
    cur: list[str] = []
    in_code = False

    def flush() -> None:
        nonlocal cur
        if cur:
            paragraphs.append(cur)
        cur = []

    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            in_code = not in_code
            flush()
            continue
        if in_code:
            continue
        line = raw.strip()
        if not line:
            flush()
            continue
        standalone = bool(_HEADING.match(line) or _LIST.match(line))
        line = _HEADING.sub("", line)
        line = _LIST.sub("", line)
        line = line.lstrip("> ").strip()
        line = _LINK.sub(r"\1", line)
        line = _EMPH.sub("", line)
        if standalone:
            flush()
        for tok in line.split():
            if _PUNCT_ONLY.match(tok) and not tok.isdigit():
                # e.g. a detached "।" or "?" belongs to the previous word
                if cur:
                    cur[-1] += tok
                elif paragraphs:
                    paragraphs[-1][-1] += tok
                continue
            cur.append(tok)
        if standalone:
            flush()
    flush()
    return paragraphs


def estimate_transcript(
    text: str, project_id: str, language: Language, cfg: dict[str, Any], sent_cfg: dict[str, Any]
) -> Transcript:
    wps = cfg["words_per_second"][language.value]
    step = 1.0 / wps
    words: list[Word] = []
    t = 0.0
    for para in parse_script(text):
        for k, tok in enumerate(para):
            last = k == len(para) - 1
            words.append(
                Word(text=tok, start=round(t, 3), end=round(t + step, 3), paragraph_break=last)
            )
            t += step
            if last:
                t += cfg["paragraph_pause_s"]
            elif is_terminal(tok, sent_cfg):
                t += cfg["sentence_pause_s"]
    if not words:
        raise ValueError("script contains no spoken words")
    duration = round(words[-1].end + cfg["tail_s"], 3)
    return Transcript(
        project_id=project_id,
        language_declared=language,
        timing_source=TimingSource.ESTIMATED,
        duration_s=duration,
        words=words,
        sentences=build_sentences(words, sent_cfg),
        transcript_schema_version=TRANSCRIPT_SCHEMA_VERSION,
    )
