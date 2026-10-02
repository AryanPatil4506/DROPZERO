from typing import Literal

from pydantic import BaseModel

FlagCategory = Literal[
    "slow_hook",
    "payoff_delay",
    "repetition",
    "low_information",
    "pacing",
    "fillers",
    "silence",
    "visual_monotony",
    "model_risk",
]
Action = Literal["CUT", "MOVE", "SHORTEN", "REWRITE", "ADD_HOOK", "ADD_VISUAL", "KEEP"]


class Evidence(BaseModel):
    label: str
    value: float | str
    unit: str | None = None
    ref_start: float | None = None  # e.g. the earlier section a repeat matches
    ref_end: float | None = None


class Edit(BaseModel):
    id: str
    flag_id: str
    action: Action
    start: float
    end: float
    target_time: float | None = None  # MOVE destination (original timeline)
    reason: str
    rewrite_text: str | None = None
    simulatable: bool  # CUT/MOVE change the feature sequence; others are advice only


class Flag(BaseModel):
    id: str
    start: float
    end: float
    severity: Literal["high", "medium"]
    category: FlagCategory
    # where the flag comes from: the validated model, an (unvalidated) evidence rule, or both
    source: Literal["model", "rule", "model+rule"]
    risk_score: float  # 0..1, DROPZERO internal score
    title: str
    explanation: str
    evidence: list[Evidence]
    secondary_categories: list[FlagCategory] = []
    edit_ids: list[str] = []


class PromiseCheck(BaseModel):
    """Feature #8/#20: when is the title's promise first addressed?"""

    title: str
    first_mention_s: float | None  # first sentence at/above the mention threshold
    first_mention_text: str | None
    best_match_s: float | None
    best_similarity: float | None


class FlagsResponse(BaseModel):
    project_id: str
    model_version: str
    rules_version: str
    promise: PromiseCheck
    flags: list[Flag]
    edits: list[Edit]
