from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.transcript import TimingSource


class RepetitionMatch(BaseModel):
    """Evidence: a sentence in this segment closely matches an earlier sentence."""

    sentence_idx: int
    start: float
    end: float
    matched_sentence_idx: int
    matched_start: float
    matched_end: float
    similarity: float


class PhraseRepeat(BaseModel):
    """Evidence: an exact phrase said in this segment that was already said earlier."""

    phrase: str
    at: float  # start of the sentence that says it here
    count: int  # times said in the whole video
    first_at: float  # start of the sentence that first says it


class PhraseStat(BaseModel):
    phrase: str
    count: int
    times: list[float]  # sentence starts, first 10


class SegmentTextFeatures(BaseModel):
    segment_id: str
    index: int
    start: float
    end: float
    kind: Literal["speech", "silence"]

    # pacing (feature #18): relative to this video's own baseline, not a universal norm
    word_count: int
    words_per_second: float  # words / segment duration (viewer time, pauses included)
    pace_ratio: float | None  # words_per_second / video median over speech segments

    # fillers (feature #17)
    filler_count: int
    filler_ratio: float | None  # filler tokens / word_count
    fillers: list[str]
    repeated_word_count: int  # immediate duplicates: "the the", "toh toh"

    # structure of statements
    question_count: int
    question_density: float | None  # questions / sentences in segment
    claim_count: int
    claim_density: float | None  # sentences with a concrete number / sentences

    # semantic (features #13, #14, #19); scales are specific to the embedding model
    semantic_novelty: float | None  # 1 - max cosine to any earlier speech segment
    information_gain: float | None  # 1 - cosine to centroid of the preceding context window
    repetition_similarity: float | None  # max cosine to segments ending >= min_gap_s earlier
    repetition_match_segment: int | None  # index of that earlier segment
    repetition_count: int  # earlier segments above segment_threshold ("repeated N times")
    repeated_sentence_ratio: float | None  # share of words in sentences matching earlier ones
    repetition_matches: list[RepetitionMatch]
    topic_shift: float | None  # 1 - cosine to the previous speech segment
    topic_boundary: bool  # a new topic section starts here

    # delivery evidence (text-1.1; not used by the model). None in script mode for pauses.
    longest_pause_s: float | None = None  # longest gap between consecutive words
    longest_pause_at: float | None = None
    long_pause_count: int = 0  # gaps >= pauses.long_pause_s
    phrase_repeats: list[PhraseRepeat] = []  # repeated exact phrases said again here


class TopicSection(BaseModel):
    index: int
    start: float
    end: float
    first_segment: int
    last_segment: int


class TextFeatureSet(BaseModel):
    project_id: str
    feature_schema_version: str
    embedding_model: str
    config_hash: str
    timing_source: TimingSource  # "estimated" in script mode: timing-based features are estimates
    baseline_words_per_second: float | None
    segments: list[SegmentTextFeatures]
    topics: list[TopicSection]
    repeated_phrases: list[PhraseStat] = []  # most repeated exact phrases in the video
