"""Words -> sentences. Deterministic.

Ends a sentence at terminal punctuation (. ? ! and the Hindi danda ।), at long silences, and —
for unpunctuated speech such as Hinglish ASR output — at pauses once the sentence has run long
enough to avoid tiny fragments.
"""

from typing import Any

from backend.app.schemas.transcript import Sentence, SentenceEnd, Word

_CLOSERS = "\"'”’)]}»"


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
                long_enough = w.end - words[start].start >= cfg["pause_min_sentence_s"]
                if w.paragraph_break or (gap >= cfg["pause_gap_s"] and long_enough):
                    reason = "pause"
        if reason is None:
            continue
        sentences.append(
            Sentence(
                idx=len(sentences),
                start=words[start].start,
                end=w.end,
                text=" ".join(x.text.strip() for x in words[start : i + 1]).strip(),
                word_start=start,
                word_end=i + 1,
                end_reason=reason,
            )
        )
        start = i + 1
    return sentences
