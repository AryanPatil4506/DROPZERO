// Mirrors docs/frontend-brief.md §4 and backend/app/schemas/. All times are seconds (float).

export type Category = "tech" | "education" | "vlog";
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
  segments: { segment_id: string; index: number; start: number; end: number; p_drop: number; risk: Risk }[];
}

export type FlagCategory =
  | "slow_hook"
  | "repetition"
  | "low_information"
  | "payoff_delay"
  | "visual_monotony"
  | "pacing"
  | "fillers"
  | "silence";

export interface Evidence {
  label: string;
  value: number | string;
  unit?: string;
  ref_start?: number;
  ref_end?: number;
}

export interface Flag {
  id: string;
  start: number;
  end: number;
  severity: "high" | "medium";
  category: FlagCategory;
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
}

export interface FlagsResponse extends MockMarker {
  flags: Flag[];
  edits: Edit[];
}

export interface Simulation extends MockMarker {
  label: string;
  applied_edit_ids: string[];
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
}

export interface Validation extends MockMarker {
  dataset: string;
  model_version: string;
  n_videos_test: number;
  split: string;
  metrics: Metrics;
  baseline: Metrics & { name: string };
  detection: { tolerance_s: number; precision: number; recall: number; f1: number; detected: number; total: number };
  examples: {
    video_id: string;
    title: string;
    actual: { t: number; retention: number }[];
    predicted: { t: number; retention: number }[];
    drops: { t: number; detected: boolean }[];
  }[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
