"""Transcript + segments -> TextFeatureSet. Deterministic given the embedder.

Silence segments get zero counts and None for ratios/semantic features; they are skipped when
computing semantic comparisons so a music intro never "repeats" anything.
"""

import statistics
from typing import Any

from backend.app.config import config_hash
from backend.app.features.text import semantic
from backend.app.features.text.embedder import Embedder
from backend.app.features.text.lexical import (
    Lexicon,
    find_fillers,
    has_number_claim,
    is_question,
    repeated_words,
    tokens,
)
from backend.app.schemas.features import (
    RepetitionMatch,
    SegmentTextFeatures,
    TextFeatureSet,
    TopicSection,
)
from backend.app.schemas.segment import Segment
from backend.app.schemas.transcript import Transcript
from backend.app.versions import FEATURE_SCHEMA_VERSION

R = 4  # decimals; rounding makes stored features stable across float noise


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), R)


def extract_text_features(
    t: Transcript,
    segments: list[Segment],
    embedder: Embedder,
    text_cfg: dict[str, Any],
    filler_cfg: dict[str, Any],
) -> TextFeatureSet:
    lex = Lexicon.from_config(filler_cfg, text_cfg)
    rep_cfg, nov_cfg, top_cfg = text_cfg["repetition"], text_cfg["novelty"], text_cfg["topics"]

    # word index -> sentence index
    word_sent = [0] * len(t.words)
    for s in t.sentences:
        for w in range(s.word_start, s.word_end):
            word_sent[w] = s.idx

    # ---- sentence-level lexical + repetition
    sent_tokens = [tokens(s.text) for s in t.sentences]
    sent_q = [is_question(s.text, lex) for s in t.sentences]
    sent_claim = [has_number_claim(s.text, lex) for s in t.sentences]
    sent_fillers = [find_fillers(tk, lex) for tk in sent_tokens]
    eligible = [len(tk) >= rep_cfg["min_sentence_words"] for tk in sent_tokens]
    sent_emb = embedder.embed([s.text for s in t.sentences])
    matches = (
        semantic.sentence_matches(
            sent_emb,
            [s.start for s in t.sentences],
            [s.end for s in t.sentences],
            eligible,
            rep_cfg["min_gap_s"],
            rep_cfg["sentence_threshold"],
        )
        if t.sentences
        else []
    )

    # ---- segment-level semantic, speech segments only
    speech = [s for s in segments if s.kind == "speech"]
    seg_emb = embedder.embed([s.text for s in speech])
    sp_starts = [s.start for s in speech]
    sp_ends = [s.end for s in speech]
    pos = {s.index: k for k, s in enumerate(speech)}
    if speech:
        seg_rep = semantic.segment_repetition(
            seg_emb, sp_starts, sp_ends, rep_cfg["min_gap_s"], rep_cfg["segment_threshold"]
        )
        nov = semantic.novelty(seg_emb)
        gain = semantic.information_gain(seg_emb, sp_starts, sp_ends, nov_cfg["context_window_s"])
        shift = semantic.topic_shift(seg_emb)
        bounds = {
            speech[k].index
            for k in semantic.topic_boundaries(
                seg_emb,
                sp_starts,
                top_cfg["block_size"],
                top_cfg["depth_std_k"],
                top_cfg["depth_abs_min"],
                top_cfg["min_section_s"],
            )
        }
    else:
        seg_rep, nov, gain, shift, bounds = [], [], [], [], set()

    wps = {s.index: (s.word_end - s.word_start) / max(s.duration, 1e-6) for s in speech}
    baseline = statistics.median(wps.values()) if wps else None

    out: list[SegmentTextFeatures] = []
    for seg in segments:
        # a sentence belongs to the segment holding its last word (no double counting
        # when an over-long sentence was split across segments)
        sids = [
            i for i in seg.sentence_ids if seg.word_start < t.sentences[i].word_end <= seg.word_end
        ]
        words_in = range(seg.word_start, seg.word_end)
        n_words = len(words_in)
        fillers = [f for i in sids for f in sent_fillers[i]] if sids else []
        toks = [tk for i in sids for tk in sent_tokens[i]]
        n_sent = len(sids)
        rep_words = sum(1 for w in words_in if matches and matches[word_sent[w]] is not None)
        seg_matches = []
        for i in seg.sentence_ids:
            m = matches[i] if matches else None
            if m is not None:
                a, sim = m
                s, ms = t.sentences[i], t.sentences[a]
                seg_matches.append(
                    RepetitionMatch(
                        sentence_idx=i,
                        start=s.start,
                        end=s.end,
                        matched_sentence_idx=a,
                        matched_start=ms.start,
                        matched_end=ms.end,
                        similarity=round(sim, R),
                    )
                )
        seg_matches.sort(key=lambda m: (-m.similarity, m.sentence_idx))
        k = pos.get(seg.index)
        rep = seg_rep[k] if k is not None else None
        is_speech = seg.kind == "speech"
        out.append(
            SegmentTextFeatures(
                segment_id=seg.id,
                index=seg.index,
                start=seg.start,
                end=seg.end,
                kind=seg.kind,
                word_count=n_words,
                words_per_second=round(n_words / max(seg.duration, 1e-6), R),
                pace_ratio=_r(wps[seg.index] / baseline) if is_speech and baseline else None,
                filler_count=len(fillers),
                filler_ratio=_r(len(fillers) / n_words) if n_words else None,
                fillers=fillers,
                repeated_word_count=repeated_words(toks),
                question_count=sum(sent_q[i] for i in sids),
                question_density=_r(sum(sent_q[i] for i in sids) / n_sent) if n_sent else None,
                claim_count=sum(sent_claim[i] for i in sids),
                claim_density=_r(sum(sent_claim[i] for i in sids) / n_sent) if n_sent else None,
                semantic_novelty=_r(nov[k]) if k is not None else None,
                information_gain=_r(gain[k]) if k is not None else None,
                repetition_similarity=_r(rep.similarity) if rep else None,
                repetition_match_segment=(
                    speech[rep.match].index if rep and rep.match is not None else None
                ),
                repetition_count=rep.count if rep else 0,
                repeated_sentence_ratio=_r(rep_words / n_words) if n_words else None,
                repetition_matches=seg_matches[: rep_cfg["max_matches_per_segment"]],
                topic_shift=_r(shift[k]) if k is not None else None,
                topic_boundary=seg.index in bounds,
            )
        )

    # topic sections over the whole timeline (silence attaches to the section it falls in)
    starts_idx = [0] + sorted(bounds)
    topics = []
    for n, first in enumerate(starts_idx):
        last = (starts_idx[n + 1] - 1) if n + 1 < len(starts_idx) else len(segments) - 1
        if not segments:
            break
        topics.append(
            TopicSection(
                index=n,
                start=segments[first].start,
                end=segments[last].end,
                first_segment=first,
                last_segment=last,
            )
        )

    return TextFeatureSet(
        project_id=t.project_id,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        embedding_model=embedder.model_id(),
        config_hash=config_hash([text_cfg, filler_cfg]),
        timing_source=t.timing_source,
        baseline_words_per_second=_r(baseline),
        segments=out,
        topics=topics,
    )
