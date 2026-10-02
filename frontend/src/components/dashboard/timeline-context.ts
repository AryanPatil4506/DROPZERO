import { createContext, useContext } from "react";

export interface TimeRange {
  start: number;
  end: number;
}

/** An edit the creator made in the editor: cut, trim start/end or speed-up (kept in the browser;
 * never applied to the file). Simulated by the backend's exposure model. */
export interface CustomCut extends TimeRange {
  id: string;
  action: "CUT" | "TRIM_START" | "TRIM_END" | "SPEED";
  factor?: number;
}

/** One shared timeline: every panel reads and sets the same current time and selection. */
export interface TimelineState {
  duration: number;
  time: number;
  seek: (t: number) => void;
  playing: boolean;
  setPlaying: (playing: boolean) => void;
  restart: () => void;
  selectedFlagId: string | null;
  selectFlag: (id: string | null) => void;
  /** "Show me what to cut": the edit range highlighted on curve, segment bar and transcript. */
  cut: TimeRange | null;
  setCut: (range: TimeRange | null) => void;
  /** Visible window of the timeline (zoom). */
  view: TimeRange;
  zoom: number;
  setZoom: (zoom: number) => void;

  /* ---- edit plan (an edit decision list; the original file is never modified) ---- */
  acceptedEditIds: string[];
  toggleEdit: (id: string) => void;
  setAcceptedEditIds: (ids: string[]) => void;
  customCuts: CustomCut[];
  addCustomCut: (range: TimeRange & { action?: CustomCut["action"]; factor?: number }) => void;
  removeCustomCut: (id: string) => void;
  /** Playback skips accepted cuts, so the creator can hear the edited flow. */
  previewEdited: boolean;
  setPreviewEdited: (on: boolean) => void;
  /** Ranges skipped while previewing (accepted CUT/SHORTEN edits + custom cuts), sorted. */
  skipRanges: TimeRange[];
}

export const TimelineContext = createContext<TimelineState | null>(null);

export function useTimeline(): TimelineState {
  const ctx = useContext(TimelineContext);
  if (!ctx) throw new Error("useTimeline must be used inside the dashboard");
  return ctx;
}

export const overlaps = (a: TimeRange, b: TimeRange) => a.start < b.end && b.start < a.end;

/** If t falls inside a skipped range, return where playback should jump to. */
export function skipTarget(t: number, ranges: TimeRange[]): number | null {
  for (const r of ranges) if (t >= r.start && t < r.end - 0.05) return r.end;
  return null;
}
