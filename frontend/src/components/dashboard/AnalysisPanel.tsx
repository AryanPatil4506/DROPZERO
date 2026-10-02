import { useState } from "react";
import type { Flag, Project, Segment, TextFeatures } from "../../api/types";
import { CATEGORY_LABEL, LANGUAGE_LABEL } from "../../lib/format";
import { IconChevron } from "../icons";
import { Segmented } from "../ui";
import { useTimeline } from "./timeline-context";

/** Compact analysis card: playback mode + measured, deterministic numbers (no model output here). */
export default function AnalysisPanel({
  project,
  flags,
  segments,
  features,
}: {
  project: Project;
  flags: Flag[];
  segments: Segment[];
  features: TextFeatures | null;
}) {
  const { previewEdited, setPreviewEdited, skipRanges } = useTimeline();
  const [more, setMore] = useState(false);
  const high = flags.filter((f) => f.severity === "high").length;
  const fillers = features?.segments.reduce((n, s) => n + s.filler_count, 0);
  const pace = features?.baseline_words_per_second;
  const cutSeconds = skipRanges.reduce((n, r) => n + (r.end - r.start), 0);

  const stats = [
    { label: "Flags", value: flags.length ? `${flags.length} (${high} high)` : "—" },
    { label: "Fillers", value: fillers == null ? "—" : String(fillers) },
    { label: "Pace", value: pace == null ? "—" : `${pace.toFixed(1)} w/s` },
  ];
  const extra = [
    { label: "Segments", value: String(segments.length) },
    { label: "Topics", value: String(features?.topics.length ?? "—") },
    { label: "Language", value: LANGUAGE_LABEL[project.language] ?? project.language },
    { label: "Category", value: CATEGORY_LABEL[project.category] ?? project.category },
  ];

  return (
    <section className="glass rounded-[26px] p-3.5" aria-label="Analysis summary">
      <div className="flex items-center justify-between gap-2 pl-1">
        <h2 className="text-[16px] font-medium tracking-tight">Analysis</h2>
        <Segmented
          label="Playback mode"
          value={previewEdited ? "edited" : "full"}
          onChange={(v) => setPreviewEdited(v === "edited" && skipRanges.length > 0)}
          options={[
            { value: "full", label: "Full" },
            { value: "edited", label: skipRanges.length ? `Edited −${Math.round(cutSeconds)}s` : "Edited" },
          ]}
        />
      </div>
      <dl className="mt-2.5 grid grid-cols-3 gap-1.5">
        {(more ? [...stats, ...extra] : stats).map((s) => (
          <div key={s.label} className="rounded-xl bg-white/[0.05] px-2.5 py-1.5">
            <dt className="text-[10.5px] text-ink-3">{s.label}</dt>
            <dd className="truncate text-[13px] font-medium text-ink tabular-nums">{s.value}</dd>
          </div>
        ))}
      </dl>
      <button type="button" onClick={() => setMore((m) => !m)} className="mx-auto mt-1.5 flex items-center gap-1 text-[12px] text-ink-3 hover:text-ink" aria-expanded={more}>
        <IconChevron className={`size-3 transition-transform ${more ? "-rotate-90" : "rotate-90"}`} />
        {more ? "Show less" : "Show more"}
      </button>
    </section>
  );
}
