"""Words -> sentences. Deterministic.

Ends a sentence at terminal punctuation (. ? ! and the Hindi danda ।), at long silences, and —
for unpunctuated speech such as Hinglish ASR output — at pauses once the sentence has run long
enough to avoid tiny fragments.
"""

from typing import Any

from backend.app.schemas.transcript import Sentence, SentenceEnd, Word

_CLOSERS = "\"'”’)]}»"


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF


def join_tokens(tokens) -> str:
    """Join word tokens with spaces, except between two CJK characters (Chinese captions are
    tokenised per character and must not become spaced-out text)."""
    out = ""
    for tok in (t.strip() for t in tokens):
        if not tok:
            continue
        if out and not (_is_cjk(out[-1]) and _is_cjk(tok[0])):
            out += " "
        out += tok
    return out


def is_terminal(token: str, cfg: dict[str, Any]) -> bool:
    t = token.strip().rstrip(_CLOSERS)
    if not t:
        return False
    if t.lower() in cfg["abbreviations"]:
        return False
    return t[-1] in cfg["terminal_punctuation"]


def build_sentences(words: list[Word], cfg: dict[str, Any]) -> list[Sentence]:
    sentences: list[Sentence] = []
    start = 0
    n = len(words)
    for i, w in enumerate(words):
        reason: SentenceEnd | None = None
        if i == n - 1:
            reason = "end"
        else:
            gap = words[i + 1].start - w.end
            if is_terminal(w.text, cfg):
                reason = "punct"
            elif gap >= cfg["silence_gap_s"]:
                reason = "silence"
            else:
                run = w.end - words[start].start
                long_enough = run >= cfg["pause_min_sentence_s"]
                if w.paragraph_break or (gap >= cfg["pause_gap_s"] and long_enough):
                    reason = "pause"
                elif w.phrase_break and run >= cfg["phrase_min_sentence_s"]:
                    # unpunctuated ASR (common in Hindi): Whisper's own phrase boundary
                    reason = "phrase"
                elif run >= cfg["max_sentence_s"]:
                    reason = "max_length"
        if reason is None:
            continue
        sentences.append(
            Sentence(
                idx=len(sentences),
                start=words[start].start,
                end=w.end,
                text=join_tokens(x.text for x in words[start : i + 1]),
                word_start=start,
                word_end=i + 1,
                end_reason=reason,
            )
        )
        start = i + 1
    return sentences
