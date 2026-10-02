/** Seconds (float) → "mm:ss". Formatting happens only at the UI edge. */
export function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export const range = (start: number, end: number) => `${mmss(start)}–${mmss(end)}`;

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;

export function evidenceValue(value: number | string, unit?: string): string {
  if (typeof value === "string") return unit ? `${value} ${unit}` : value;
  if (unit === "s") return value >= 60 ? `${mmss(value)}` : `${value.toFixed(value < 10 ? 1 : 0)} s`;
  const text = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return unit ? `${text} ${unit}` : text;
}

export const LANGUAGE_LABEL: Record<string, string> = { en: "English", hi: "Hindi", hinglish: "Hinglish" };
export const CATEGORY_LABEL: Record<string, string> = { tech: "Tech", education: "Education", vlog: "Vlog" };

export const FLAG_CATEGORY_LABEL: Record<string, string> = {
  slow_hook: "Slow hook",
  repetition: "Repetition",
  low_information: "Low new information",
  payoff_delay: "Delayed payoff",
  visual_monotony: "Visual monotony",
  pacing: "Pacing",
  fillers: "Filler words",
  silence: "Silence",
};

export const ACTION_LABEL: Record<string, string> = {
  CUT: "Cut",
  MOVE: "Move",
  SHORTEN: "Shorten",
  REWRITE: "Rewrite",
  ADD_HOOK: "Add hook",
  ADD_VISUAL: "Add visual",
  KEEP: "Keep",
};

export const STAGE_LABEL: Record<string, string> = {
  extract_audio: "Extract audio",
  transcribe: "Transcribe",
  estimate_timing: "Estimate timing",
  segment: "Segment",
  text_features: "Analyse text",
  av_features: "Analyse audio & video",
  predict: "Predict",
  recommend: "Recommendations",
};

/** "Cut 01:43–01:58: repeated explanation" style creator copy for an edit. */
export function editSentence(action: string, start: number, end: number, targetTime: number | null): string {
  const verb = ACTION_LABEL[action] ?? action;
  if (action === "MOVE" && targetTime != null) return `${verb} ${range(start, end)} to ${mmss(targetTime)}`;
  return `${verb} ${range(start, end)}`;
}
