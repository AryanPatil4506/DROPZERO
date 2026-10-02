"""Promise ledger: what the video promises early on, and when (or whether) it pays off.

Deterministic: cue phrases (config/promises.yaml, EN / Hinglish / Hindi) find promise sentences
in the opening; LaBSE similarity finds the first later sentence that delivers on each one.
"""

import numpy as np

from backend.app.features.text.embedder import Embedder
from backend.app.features.text.lexical import tokens
from backend.app.schemas.flags import PromiseCheck, PromiseItem
from backend.app.schemas.transcript import Transcript


def _strip_cues(text: str, cues: list[str]) -> str:
    """The promised thing is what follows the promise phrase: "By the end of this video you will
    see <the agent book a table>". Keep the text after the last cue (if it has >= 3 words)."""
    low = text.lower()
    end = max((low.find(c) + len(c) for c in cues if c in low), default=-1)
    rest = text[end:].strip(" ,.:;-") if end >= 0 else ""
    return rest if len(rest.split()) >= 3 else text


def _has_cue(text: str, cue_tokens: list[list[str]]) -> bool:
    """Whole-word match ("today i" must not match "today is")."""
    toks = tokens(text)
    return any(toks[i : i + len(c)] == c for c in cue_tokens for i in range(len(toks) - len(c) + 1))


def build_ledger(
    t: Transcript, title_check: PromiseCheck, embedder: Embedder, cfg: dict
) -> list[PromiseItem]:
    cues = [c.lower() for lst in cfg["cues"].values() for c in lst]
    ledger: list[PromiseItem] = []

    # the title: "addressed" = first sentence that matches it (from the title check)
    if len(title_check.title.split()) >= 3:
        at = title_check.first_mention_s
        s = next((x for x in t.sentences if at is not None and x.start <= at < x.end + 1e-6), None)
        ledger.append(
            PromiseItem(
                text=title_check.title,
                source="title",
                made_at=0.0,
                made_end=0.0,
                payoff_at=at,
                payoff_end=s.end if s else None,
                payoff_text=s.text if s else None,
                similarity=None,
                delay_s=at,
                status="open" if at is None else "late" if at > cfg["late_delay_s"] else "kept",
            )
        )

    cue_tokens = [tokens(c) for c in cues]
    promises = [
        s for s in t.sentences if s.start < cfg["window_s"] and _has_cue(s.text, cue_tokens)
    ][: cfg["max_promises"]]
    if not promises or not t.sentences:
        return ledger
    targets = [_strip_cues(p.text, cues) for p in promises]
    emb = embedder.embed(targets + [s.text for s in t.sentences])
    pe, se = emb[: len(promises)], emb[len(promises) :]
    sims = pe @ se.T
    for k, p in enumerate(promises):
        later = [i for i, s in enumerate(t.sentences) if s.start >= p.end + cfg["min_gap_s"]]
        # a payoff is not a paraphrase of the promise: accept the first later sentence that is
        # either above the paraphrase threshold, or clearly stands out from this promise's
        # similarity to the rest of the video (mean + k*std), above an absolute floor
        thr = cfg["match_threshold"]
        if len(later) >= 5:
            v = sims[k, later]
            thr = min(
                thr, max(cfg["relative_floor"], float(v.mean() + cfg["relative_std_k"] * v.std()))
            )
        hit = next((i for i in later if sims[k, i] >= thr), None)
        if hit is None:
            best = later[int(np.argmax(sims[k, later]))] if later else None
            ledger.append(
                PromiseItem(
                    text=p.text,
                    source="intro",
                    made_at=p.start,
                    made_end=p.end,
                    payoff_at=None,
                    payoff_end=None,
                    payoff_text=None,
                    similarity=round(float(sims[k, best]), 4) if best is not None else None,
                    delay_s=None,
                    status="open",
                )
            )
            continue
        s = t.sentences[hit]
        delay = s.start - p.start
        ledger.append(
            PromiseItem(
                text=p.text,
                source="intro",
                made_at=p.start,
                made_end=p.end,
                payoff_at=s.start,
                payoff_end=s.end,
                payoff_text=s.text,
                similarity=round(float(sims[k, hit]), 4),
                delay_s=round(delay, 1),
                status="late" if delay > cfg["late_delay_s"] else "kept",
            )
        )
    return ledger
