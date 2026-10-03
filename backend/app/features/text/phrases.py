"""Pure features from word timestamps and tokens: pauses between words, repeated exact phrases.

Both are evidence next to the model and the semantic checks; the model does not use them.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from backend.app.schemas.transcript import Word


@dataclass(frozen=True)
class Pauses:
    longest_pause_s: float | None
    longest_pause_at: float | None  # when the longest pause starts
    long_pause_count: int


def segment_pauses(words: list[Word], long_pause_s: float) -> Pauses:
    """Gaps between consecutive words (all in one segment, in time order)."""
    gaps = [(b.start - a.end, a.end) for a, b in zip(words, words[1:], strict=False)]
    gaps = [(g, at) for g, at in gaps if g > 0]
    if not gaps:
        return Pauses(0.0 if len(words) > 1 else None, None, 0)
    g, at = max(gaps, key=lambda x: (x[0], -x[1]))
    return Pauses(round(g, 3), round(at, 3), sum(1 for x, _ in gaps if x >= long_pause_s))


@dataclass(frozen=True)
class Occurrence:
    sentence: int  # sentence index
    pos: int  # token position inside the sentence


def phrase_occurrences(
    sentence_tokens: list[list[str]],
    fillers: frozenset[str],
    stopwords: frozenset[str],
    cfg: dict[str, Any],
) -> dict[str, list[Occurrence]]:
    """Every eligible n-gram -> its occurrences in time order. Phrases never cross sentences."""
    n, max_stop = cfg["n"], cfg["max_stopwords"]
    occ: dict[str, list[Occurrence]] = defaultdict(list)
    for si, toks in enumerate(sentence_tokens):
        for i in range(len(toks) - n + 1):
            gram = toks[i : i + n]
            if any(t in fillers for t in gram):
                continue
            if sum(t in stopwords for t in gram) > max_stop:
                continue
            occ[" ".join(gram)].append(Occurrence(si, i))
    return dict(occ)


def repeated_phrases(occ: dict[str, list[Occurrence]], min_count: int) -> list[str]:
    """Phrases said at least min_count times, most repeated first. A phrase whose every
    occurrence sits one word off a higher-ranked phrase is the same repeat (a longer repeated
    run yields overlapping trigrams) and is dropped."""
    ranked = sorted(
        (p for p, o in occ.items() if len(o) >= min_count),
        key=lambda p: (-len(occ[p]), occ[p][0].sentence, occ[p][0].pos, p),
    )
    kept: list[str] = []
    taken: set[tuple[int, int]] = set()
    for p in ranked:
        spots = {(o.sentence, o.pos) for o in occ[p]}
        covered = all((s, i - 1) in taken or (s, i + 1) in taken for s, i in spots)
        taken |= spots  # also when covered, so the next overlapping trigram is covered too
        if not covered:
            kept.append(p)
    return kept


__all__ = ["Pauses", "segment_pauses", "Occurrence", "phrase_occurrences", "repeated_phrases"]
