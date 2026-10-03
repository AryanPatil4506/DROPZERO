// Mirrors docs/frontend-brief.md §4 and backend/app/schemas/. All times are seconds (float).

export type Category = "tech" | "education" | "vlog" | "music" | "other";
export type Language = "en" | "hi" | "hinglish";
export type TimingSource = "asr" | "estimated";
export type Risk = "low" | "medium" | "high";

/** Contract mocks carry this field; its presence means the numbers are placeholders. */
export interface MockMarker {
  _mock?: string;
}

export interface Project {
  id: string;
  title: string;
  creator: string | null;
  category: Category;
  language: Language;
  target_audience: string | null;
  source_type: "video" | "script" | null;
  duration_s: number | null;
  thumbnail_ref: string | null;
  status: string;
  warnings: string[];
  created_at: string;
  uploaded_at?: string | null;
  source_filename?: string | null;
}

export interface NewProject {
  title: string;
  category: Category;
  language: Language;
  creator?: string;
  target_audience?: string;
}

export interface Job {
  id: string;
  project_id: string;
  status: "queued" | "running" | "done" | "failed";
  stages: string[];
  stage: string | null;
  progress: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface Word {
  text: string;
  start: number;
  end: number;
  confidence: number | null;
}

export interface Sentence {
  idx: number;
  start: number;
  end: number;
  text: string;
  word_start: number;
  word_end: number;
}

export interface Transcript {
  project_id: string;
  language_declared: Language;
  timing_source: TimingSource;
  duration_s: number;
  words: Word[];
  sentences: Sentence[];
}

export interface Segment {
  id: string;
  index: number;
  kind: "speech" | "silence";
  start: number;
  end: number;
  text: string;
  boundary: string;
  timing_source: TimingSource;
}

export interface SegmentTextFeatures {
  segment_id: string;
  index: number;
  start: number;
  end: number;
  words_per_second: number | null;
  pace_ratio: number | null;
  filler_count: number;
  fillers: string[];
  semantic_novelty: number | null;
  repetition_similarity: number | null;
  topic_boundary: boolean;
}

export interface Topic {
  index: number;
  start: number;
  end: number;
  first_segment: number;
  last_segment: number;
  label?: string; // requested in CONTRACT_REQUESTS.md
}

export interface TextFeatures {
  project_id: string;
  feature_schema_version: string;
  timing_source: TimingSource;
  baseline_words_per_second: number | null;
  segments: SegmentTextFeatures[];
  topics: Topic[];
  /** Exact three-word phrases said 3+ times (text-1.1; absent on older analyses). */
  repeated_phrases?: { phrase: string; count: number; times: number[] }[];
}

/** Video-level audio summary from GET /features/av (per-segment values are used as flag evidence). */
export interface AvFeatures {
  project_id: string;
  av_feature_schema_version: string;
  has_video: boolean;
  snr_db?: number | null;
  pitch_median_hz?: number | null;
  pitch_range_median_st?: number | null;
}

export interface CurvePoint {
  t: number;
  retention: number;
  lower: number;
  upper: number;
}

export interface Prediction extends MockMarker {
  project_id: string;
  model_version: string;
  feature_schema_version: string;
  timing_source: TimingSource;
  label: string;
  points: CurvePoint[];
  segments: {
    segment_id: string;
    index: number;
    start: number;
    end: number;
    p_drop: number;
    p_drop_low?: number;
    p_drop_high?: number;
    /** relative to a typical video at the same position */
    risk: Risk;
  }[];
}

export type FlagCategory =
  | "slow_hook"
  | "repetition"
  | "low_information"
  | "payoff_delay"
  | "visual_monotony"
  | "pacing"
  | "fillers"
  | "silence"
  | "model_risk";

export interface Evidence {
  label: string;
  value: number | string;
  unit?: string | null;
  ref_start?: number | null;
  ref_end?: number | null;
}

export interface Flag {
  id: string;
  start: number;
  end: number;
  severity: "high" | "medium";
  category: FlagCategory;
  /** model = validated retention model; rule = evidence check not validated on retention data */
  source?: "model" | "rule" | "model+rule";
  risk_score: number;
  title: string;
  explanation: string;
  evidence: Evidence[];
  secondary_categories: FlagCategory[];
  edit_ids: string[];
}

export type Action = "CUT" | "MOVE" | "SHORTEN" | "REWRITE" | "ADD_HOOK" | "ADD_VISUAL" | "KEEP";

export interface Edit {
  id: string;
  flag_id: string;
  action: Action;
  start: number;
  end: number;
  target_time: number | null;
  reason: string;
  rewrite_text: string | null;
  /** only CUT/MOVE can be simulated; others are advice */
  simulatable?: boolean;
}

export interface SegmentScore {
  index: number;
  start: number;
  end: number;
  kind: string;
  pacing: number | null;
  content: number | null;
  visual: number | null;
  audio: number | null;
  overall: number | null;
  inputs: Record<string, number | null>;
}
export interface ScoreSet {
  project_id: string;
  version: string;
  label: string;
  has_video: boolean;
  snr_db: number | null;
  segments: SegmentScore[];
}

export interface ABRequest {
  title: string;
  language: string;
  script_a: string;
  script_b: string;
  name_a: string;
  name_b: string;
}
export interface ABMetric {
  key: string;
  label: string;
  a: number | string | null;
  b: number | string | null;
  better: "lower" | "higher" | "info";
  winner: "a" | "b" | "tie" | "n/a";
  note?: string | null;
}
export interface ABVariant {
  name: string;
  duration_s: number;
  points: CurvePoint[];
  hook_flags: string[];
}
export interface ABResult {
  label: string;
  a: ABVariant;
  b: ABVariant;
  metrics: ABMetric[];
  summary: string;
}

export interface PromiseCheck {
  title: string;
  first_mention_s: number | null;
  first_mention_text: string | null;
  best_match_s: number | null;
  best_similarity: number | null;
}

/** One promise made in the title or opening, and when (or whether) it pays off. */
export interface PromiseItem {
  text: string;
  source: "title" | "intro";
  made_at: number;
  made_end: number;
  payoff_at: number | null;
  payoff_end: number | null;
  payoff_text: string | null;
  similarity: number | null;
  delay_s: number | null;
  /** kept = on time, late = paid off late, open = never paid off (open loop) */
  status: "kept" | "late" | "open";
}

export interface FlagsResponse extends MockMarker {
  project_id?: string;
  model_version?: string;
  rules_version?: string;
  promise?: PromiseCheck;
  ledger?: PromiseItem[];
  flags: Flag[];
  edits: Edit[];
}

export type CustomAction = "CUT" | "TRIM_START" | "TRIM_END" | "SPEED";
/** An edit made by the creator in the editor (simulated by the exposure model). */
export interface CustomEdit {
  action: CustomAction;
  start: number;
  end: number;
  /** SPEED only, e.g. 1.5 */
  factor?: number;
}

/** LLM narration of one flag; numbers are checked against the evidence (else template). */
export interface Explanation {
  flag_id: string;
  source: "llm" | "template";
  model: string | null;
  reason: string;
  why_viewers_leave: string;
  fix: string;
  rewrite?: string | null;
  rejected?: string[];
}

export interface Simulation extends MockMarker {
  label: string;
  method?: string;
  applied_custom?: CustomEdit[];
  applied_edit_ids: string[];
  /** overlapping or advice-only edits that were not applied */
  skipped_edit_ids?: string[];
  original: CurvePoint[];
  simulated: CurvePoint[];
  original_duration_s: number;
  simulated_duration_s: number;
  delta: { end_retention_pp: number; avg_retention_pp: number };
}

export interface Metrics {
  mae: number;
  rmse: number;
  pearson: number;
  spearman: number;
  hazard_spearman_pooled?: number;
  hazard_spearman_within_video_mean?: number;
}

export interface Detection {
  precision: number;
  recall: number;
  f1: number;
  detected: number;
  total: number;
  predicted?: number;
  median_delay_s?: number | null;
}

export interface LlmBaselineMethod {
  precision: number;
  recall: number;
  drops_found: number;
  drops_total: number;
  points_named: number;
}

export interface LlmBaseline {
  what: string;
  lectures: number;
  k: number;
  llm_model: string;
  note: string;
  methods: Record<"dropzero" | "llm" | "baseline", LlmBaselineMethod>;
}

export interface Validation extends MockMarker {
  dataset: string;
  model_version: string;
  feature_schema_version?: string;
  n_videos_train?: number;
  n_videos_test: number;
  split: string;
  metrics: Metrics;
  baseline: Metrics & { name: string };
  detection: Detection & { tolerance_s: number; major_drop_hazard?: number };
  baseline_detection?: Detection;
  band?: { quantiles: number[]; test_coverage: number };
  ablations?: Record<string, { mae: number; hazard_spearman_pooled: number; detection_f1: number }>;
  /** "Why not just ask a chatbot?": top-k drop points per lecture from DROPZERO, a plain LLM
   * (timestamped transcript only) and the position baseline, scored the same way. */
  llm_baseline?: LlmBaseline;
  examples: {
    video_id: string;
    title: string;
    actual: { t: number; retention: number }[];
    predicted: { t: number; retention: number }[];
    drops: { t: number; detected: boolean }[];
  }[];
}

/** "Rewrite this section": the local LLM tightens the flagged lines; refused if it changes the
 * meaning, isn't shorter, adds numbers, or uses the wrong script (source = "none"). */
export interface Rewrite {
  flag_id: string;
  start: number;
  end: number;
  source: "llm" | "none";
  model: string | null;
  original: string;
  rewrite: string | null;
  what_changed?: string | null;
  original_words: number;
  rewrite_words?: number | null;
  meaning_similarity?: number | null;
  /** from this video's own speaking rate; an estimate */
  est_seconds_saved?: number | null;
  rejected: string[];
}

/** Before/after render of an edit plan (the original file is never modified). */
export interface RenderPiece {
  start: number;
  end: number;
  factor: number;
}
export interface RenderPlan {
  pieces: RenderPiece[];
  applied_edit_ids: string[];
  skipped_edit_ids: string[];
  applied_custom: CustomEdit[];
  moved_edit_ids: string[];
  source_duration_s: number;
  output_duration_s: number;
}
export interface RenderStatus {
  render_id: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  encoder: string | null;
  seconds: number | null;
  plan: RenderPlan | null;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
