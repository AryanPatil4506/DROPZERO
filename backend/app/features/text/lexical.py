"""Pure, language-aware token features: fillers, questions, number claims, duplicated words.

Tokenisation splits on whitespace and strips punctuation instead of using \\w, because Python's
\\w does not match Devanagari vowel signs and would break Hindi words apart.
"""

from dataclasses import dataclass
from typing import Any

_PUNCT = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~।॥“”‘’…—–«»"


def tokens(text: str) -> list[str]:
    out = []
    for raw in text.split():
        t = raw.strip(_PUNCT).lower()
        if t:
            out.append(t)
    return out


def _union(d: dict[str, list[str]]) -> set[str]:
    return {w.lower() for lst in d.values() for w in lst}


@dataclass(frozen=True)
class Lexicon:
    filler_words: frozenset[str]
    filler_phrases: tuple[tuple[str, ...], ...]  # longest first
    filler_initial: frozenset[str]
    interrogatives: frozenset[str]
    question_tags: frozenset[str]
    number_words: frozenset[str]

    @classmethod
    def from_config(cls, fillers: dict[str, Any], text_cfg: dict[str, Any]) -> "Lexicon":
        phrases = {tuple(p.lower().split()) for lst in fillers["phrases"].values() for p in lst}
        return cls(
            filler_words=frozenset(_union(fillers["words"])),
            filler_phrases=tuple(sorted(phrases, key=lambda p: (-len(p), p))),
            filler_initial=frozenset(_union(fillers["sentence_initial"])),
            interrogatives=frozenset(_union(text_cfg["questions"]["interrogatives"])),
            question_tags=frozenset(_union(text_cfg["questions"]["tags"])),
            number_words=frozenset(_union(text_cfg["claims"]["number_words"])),
        )


def find_fillers(sentence_tokens: list[str], lex: Lexicon) -> list[str]:
    found: list[str] = []
    i = 0
    n = len(sentence_tokens)
    while i < n:
        for p in lex.filler_phrases:
            if tuple(sentence_tokens[i : i + len(p)]) == p:
                found.append(" ".join(p))
                i += len(p)
                break
        else:
            t = sentence_tokens[i]
            if t in lex.filler_words or (i == 0 and t in lex.filler_initial):
                found.append(t)
            i += 1
    return found


def repeated_words(toks: list[str]) -> int:
    return sum(1 for a, b in zip(toks, toks[1:], strict=False) if a == b)


def is_question(sentence_text: str, lex: Lexicon) -> bool:
    s = sentence_text.strip().rstrip("\"'”’)")
    if s.endswith("?"):
        return True
    if s.endswith((".", "!", "।")):
        return False
    toks = tokens(s)
    if not toks:
        return False
    # unpunctuated (typical of Hinglish ASR): use leading interrogative / trailing tag word
    return toks[0] in lex.interrogatives or toks[-1] in lex.question_tags


def has_number_claim(sentence_text: str, lex: Lexicon) -> bool:
    return any(any(c.isdigit() for c in t) or t in lex.number_words for t in tokens(sentence_text))
