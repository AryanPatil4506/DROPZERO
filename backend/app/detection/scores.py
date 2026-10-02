"""Segment score lanes: pacing, content, visual engagement, audio clarity (0-100 each).

DROPZERO internal scores, NOT validated against retention data. Transparent formulas over
features we already measure, mostly relative to this video's own distribution (so a calm
lecture is not judged against a hyper-edited vlog). Inputs are returned with every score.
"""

import numpy as np
from pydantic import BaseModel

from backend.app.schemas.av_features import AVFeatureSet
from backend.app.schemas.features import TextFeatureSet
from backend.app.schemas.segment import Segment

SCORES_VERSION = "scores-1.0"
LABEL = (
    "DROPZERO internal scores (0-100), relative to this video. Not validated against retention "
    "data; hover a block to see what each score is made of."
)


class SegmentScore(BaseModel):
    index: int
    start: float
    end: float
    kind: str
    pacing: float | None
    content: float | None
    visual: float | None
    audio: float | None
    overall: float | None
    inputs: dict[str, float | None]


class ScoreSet(BaseModel):
    project_id: str
    version: str
    label: str
    has_video: bool
    snr_db: float | None  # video-level: speech loudness above the noise floor
    segments: list[SegmentScore]


def _pct(values: list[float]):
    arr = np.sort(np.array([v for v in values if v is not None], dtype=float))

    def f(x):
        if x is None or len(arr) == 0:
            return None
        return float(np.searchsorted(arr, x, side="right") / len(arr))

    return f


def _r(x):
    return None if x is None else round(float(np.clip(x, 0, 100)), 1)


def compute_scores(
    segments: list[Segment], tf: TextFeatureSet, av: AVFeatureSet | None, cfg: dict
) -> ScoreSet:
    feats = {f.index: f for f in tf.segments}
    avs = {a.index: a for a in av.segments} if av else {}
    sp = [f for f in tf.segments if f.kind == "speech"]
    p_nov = _pct([f.semantic_novelty for f in sp])
    p_gain = _pct([f.information_gain for f in sp])
    p_vis = _pct([a.visual_change_mean for a in avs.values()])
    p_var = _pct([a.energy_variation_db for a in avs.values()])
    rep_sims = [f.repetition_similarity for f in sp if f.repetition_similarity is not None]
    rep_thr = max(cfg["repetition_floor"], float(np.quantile(rep_sims, 0.9))) if rep_sims else 1.0

    out = []
    for s in segments:
        f, a = feats[s.index], avs.get(s.index)
        speech = s.kind == "speech"
        pacing = content = visual = audio = None
        if speech and f.pace_ratio is not None:
            pacing = 100 * (f.pace_ratio - 0.5) / 0.6
        if speech and f.semantic_novelty is not None and f.information_gain is not None:
            content = 100 * (0.5 * p_nov(f.semantic_novelty) + 0.5 * p_gain(f.information_gain))
            if f.repetition_similarity is not None and f.repetition_similarity >= rep_thr:
                content *= cfg["repetition_penalty"]
        if a and a.static_ratio is not None:
            visual = 100 * (
                0.4 * (1 - a.static_ratio)
                + 0.3 * min(1.0, (a.cuts_per_minute or 0) / cfg["cuts_per_minute_full"])
                + 0.3 * (p_vis(a.visual_change_mean) or 0)
            )
        if speech and a and a.silence_ratio is not None:
            clip = a.clipping_ratio or 0.0
            audio = 100 * (
                0.4 * (1 - a.silence_ratio)
                + 0.3 * (p_var(a.energy_variation_db) or 0.5)
                + 0.3 * (1 - min(1.0, clip * cfg["clipping_scale"]))
            )
            if a.energy_db is not None and a.energy_db < cfg["quiet_db"]:
                audio -= cfg["quiet_penalty"]
        parts = [x for x in (pacing, content, visual, audio) if x is not None]
        out.append(
            SegmentScore(
                index=s.index,
                start=s.start,
                end=s.end,
                kind=s.kind,
                pacing=_r(pacing),
                content=_r(content),
                visual=_r(visual),
                audio=_r(audio),
                overall=_r(np.mean([np.clip(x, 0, 100) for x in parts])) if parts else None,
                inputs={
                    "pace_vs_your_average": f.pace_ratio,
                    "new_information": f.information_gain,
                    "novelty": f.semantic_novelty,
                    "repetition_similarity": f.repetition_similarity,
                    "scene_cuts_per_minute": a.cuts_per_minute if a else None,
                    "static_share": a.static_ratio if a else None,
                    "silence_share": a.silence_ratio if a else None,
                    "loudness_vs_your_average_db": a.energy_db if a else None,
                    "clipping_share": a.clipping_ratio if a else None,
                },
            )
        )
    return ScoreSet(
        project_id=tf.project_id,
        version=SCORES_VERSION,
        label=LABEL,
        has_video=av is not None and av.has_video,
        snr_db=av.snr_db if av else None,
        segments=out,
    )
