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
    # only CUTs are simulated (exposure model); everything else is advice
    simulatable: bool


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


Status = Literal["kept", "late", "open"]


class PromiseItem(BaseModel):
    text: str
    source: Literal["title", "intro"]
    made_at: float
    made_end: float
    payoff_at: float | None
    payoff_end: float | None
    payoff_text: str | None
    similarity: float | None
    delay_s: float | None
    status: Status


class FlagsResponse(BaseModel):
    project_id: str
    model_version: str
    rules_version: str
    promise: PromiseCheck
    ledger: list[PromiseItem] = []
    flags: list[Flag]
    edits: list[Edit]
