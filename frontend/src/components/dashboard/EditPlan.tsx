import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useNavigate } from "react-router-dom";
import type { CustomEdit, Edit, Project } from "../../api/types";
import { ACTION_LABEL, editSentence, mmss, range } from "../../lib/format";
import { IconClose, IconDownload, IconVideo } from "../icons";
import { type CustomCut, useTimeline } from "./timeline-context";

const SKIPPABLE = new Set(["CUT", "SHORTEN"]);

function customLabel(c: CustomCut): string {
  if (c.action === "TRIM_START") return `Trim start → ${mmss(c.end)}`;
  if (c.action === "TRIM_END") return `Trim end from ${mmss(c.start)}`;
  if (c.action === "SPEED") return `Speed up ×${c.factor ?? 1.5} ${range(c.start, c.end)}`;
  return `Cut ${range(c.start, c.end)}`;
}

const toCustomEdits = (cuts: CustomCut[]): CustomEdit[] =>
  cuts.map((c) => ({ action: c.action, start: c.start, end: c.end, ...(c.action === "SPEED" ? { factor: c.factor ?? 1.5 } : {}) }));

/**
 * The editor: accept suggested edits, and make your own — trim the start or end, cut a range,
 * or speed a range up. Preview playback skips cuts and trims; Simulate re-estimates the curve for
 * suggested + your own edits together. Nothing here touches the original video file.
 */
export default function EditPlan({ project, edits }: { project: Project; edits: Edit[] }) {
  const navigate = useNavigate();
  const { time, duration, seek, acceptedEditIds, toggleEdit, setAcceptedEditIds, customCuts, addCustomCut, removeCustomCut, previewEdited, setPreviewEdited, skipRanges } =
    useTimeline();
  const [markIn, setMarkIn] = useState<number | null>(null);
  const simulatableAccepted = edits.filter((e) => acceptedEditIds.includes(e.id) && e.simulatable !== false).map((e) => e.id);
  const rangeReady = markIn != null && time - markIn >= 0.5;

  const addRange = (action: CustomCut["action"], factor?: number) => {
    if (markIn == null) return;
    addCustomCut({ start: markIn, end: time, action, factor });
    setMarkIn(null);
  };

  const simulate = () => {
    const custom = toCustomEdits(customCuts);
    const q = new URLSearchParams();
    q.set("edits", simulatableAccepted.join(","));
    if (custom.length) q.set("custom", JSON.stringify(custom));
    navigate(`/projects/${project.id}/simulate?${q.toString()}`);
  };

  // Render: every accepted suggestion (moves included: a render can reorder footage) + your edits.
  const isVideo = project.source_type === "video";
  const renderM = useMutation({
    mutationFn: () => api.render(project.id, acceptedEditIds, toCustomEdits(customCuts)),
    onSuccess: (st) => {
      const q = new URLSearchParams({ render: st.render_id, edits: simulatableAccepted.join(",") });
      const custom = toCustomEdits(customCuts);
      if (custom.length) q.set("custom", JSON.stringify(custom));
      navigate(`/projects/${project.id}/compare?${q.toString()}`);
    },
  });

  const exportPlan = () => {
    const plan = {
      kind: "dropzero-edit-decision-list",
      note: "Edit plan only. DROPZERO never modifies the original file.",
      project_id: project.id,
      title: project.title,
      exported_at: new Date().toISOString(),
      edits: [
        ...edits
          .filter((e) => acceptedEditIds.includes(e.id))
          .map((e) => ({ source: "suggested", id: e.id, action: e.action, start: e.start, end: e.end, target_time: e.target_time, reason: e.reason })),
        ...customCuts.map((c) => ({ source: "custom", id: c.id, action: c.action, start: c.start, end: c.end, factor: c.factor ?? null, reason: "Made in the editor" })),
      ].sort((a, b) => a.start - b.start),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `dropzero-edits-${project.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid h-full min-h-0 gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
      <ul className="scroll-thin min-h-0 space-y-1.5 overflow-y-auto pr-1" aria-label="Edit plan">
        {edits.map((e) => {
          const on = acceptedEditIds.includes(e.id);
          return (
            <li key={e.id} className={`flex items-center gap-3 rounded-2xl px-3 py-2 ${on ? "bg-accent/15" : "bg-white/[0.04]"}`}>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={`${on ? "Remove" : "Accept"} ${editSentence(e.action, e.start, e.end, e.target_time)}`}
                onClick={() => toggleEdit(e.id)}
                className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${on ? "bg-accent" : "bg-white/15"}`}
              >
                <span className={`absolute top-1 size-4 rounded-full bg-white transition-all ${on ? "left-5" : "left-1"}`} />
              </button>
              <button type="button" onClick={() => seek(e.start)} className="min-w-0 flex-1 text-left text-[13px]">
                <span className="font-medium text-ink">{editSentence(e.action, e.start, e.end, e.target_time)}</span>
                <span className="block truncate text-ink-2">{e.reason}</span>
              </button>
              <span className="shrink-0 rounded bg-white/[0.06] px-1.5 text-[10px] font-semibold tracking-wide text-ink-3">
                {ACTION_LABEL[e.action].toUpperCase()}
                {!SKIPPABLE.has(e.action) && " · not previewed"}
                {e.simulatable === false && " · advice"}
              </span>
            </li>
          );
        })}
        {customCuts.map((c) => (
          <li key={c.id} className="flex items-center gap-3 rounded-2xl border border-dashed border-accent/50 bg-accent/10 px-3 py-2">
            <span className="grid h-6 w-10 shrink-0 place-items-center rounded-full bg-accent/30 text-[10px] font-semibold text-ink">MY</span>
            <button type="button" onClick={() => seek(c.start)} className="min-w-0 flex-1 text-left text-[13px]">
              <span className="font-medium text-ink">{customLabel(c)}</span>
              <span className="block text-ink-2">
                Made by you · simulated{c.action === "SPEED" ? " · not previewed" : ""}
              </span>
            </button>
            <button type="button" aria-label={`Remove ${customLabel(c)}`} onClick={() => removeCustomCut(c.id)} className="grid size-7 place-items-center rounded-full text-ink-3 hover:bg-white/10 hover:text-ink">
              <IconClose className="size-4" />
            </button>
          </li>
        ))}
        {edits.length === 0 && customCuts.length === 0 && <li className="px-1 text-sm text-ink-3">No edits yet. Trim, cut or speed up a range to start a plan.</li>}
      </ul>

      <div className="flex flex-col gap-2">
        <p className="eyebrow px-1">Editor · playhead {mmss(time)}</p>
        <div className="flex gap-2">
          <button type="button" className="pill-ghost h-9 flex-1 px-2 text-[13px]" disabled={time < 0.5} title="Remove everything before the playhead" onClick={() => addCustomCut({ start: 0, end: time, action: "TRIM_START" })}>
            Trim start
          </button>
          <button type="button" className="pill-ghost h-9 flex-1 px-2 text-[13px]" disabled={duration - time < 0.5} title="Remove everything after the playhead" onClick={() => addCustomCut({ start: time, end: duration, action: "TRIM_END" })}>
            Trim end
          </button>
        </div>
        <div className="flex gap-2">
          <button type="button" className="pill-ghost h-9 flex-1 px-2 text-[13px]" onClick={() => setMarkIn(time)}>
            Mark in {markIn != null && <span className="text-accent tabular-nums">{mmss(markIn)}</span>}
          </button>
          <button type="button" className="pill-ghost h-9 flex-1 px-2 text-[13px]" disabled={!rangeReady} title={markIn == null ? "Mark in first" : "Cut from mark-in to the playhead"} onClick={() => addRange("CUT")}>
            Cut to here
          </button>
        </div>
        <div className="flex gap-2">
          {[1.25, 1.5].map((f) => (
            <button key={f} type="button" className="pill-ghost h-9 flex-1 px-2 text-[13px]" disabled={!rangeReady} title={markIn == null ? "Mark in first" : `Speed up mark-in → playhead ×${f}`} onClick={() => addRange("SPEED", f)}>
              Speed ×{f}
            </button>
          ))}
        </div>
        <button type="button" className="pill-ghost h-9 text-[13px]" onClick={() => setAcceptedEditIds(acceptedEditIds.length === edits.length ? [] : edits.map((e) => e.id))} disabled={edits.length === 0}>
          {acceptedEditIds.length === edits.length && edits.length > 0 ? "Clear accepted" : "Accept all suggestions"}
        </button>
        <button type="button" className={`pill-btn h-9 text-[13px] ${previewEdited ? "bg-accent text-[#160700]" : "border border-line-2 bg-white/5 text-ink hover:bg-white/10"}`} disabled={skipRanges.length === 0} onClick={() => setPreviewEdited(!previewEdited)} aria-pressed={previewEdited}>
          {previewEdited ? "Previewing with cuts" : "Preview with cuts"}
        </button>
        <button type="button" className="pill-accent h-9 text-[13px]" disabled={simulatableAccepted.length === 0 && customCuts.length === 0} onClick={simulate}>
          Simulate my edit plan
        </button>
        <button
          type="button"
          className="pill-btn h-9 border border-accent/60 bg-accent/10 text-[13px] text-ink hover:bg-accent/20"
          disabled={!isVideo || (acceptedEditIds.length === 0 && customCuts.length === 0) || renderM.isPending}
          title={isVideo ? "Build an edited copy with FFmpeg and compare it with the original" : "Rendering needs a video project"}
          onClick={() => renderM.mutate()}
        >
          <IconVideo className="size-4" />
          {renderM.isPending ? "Starting render…" : "Render edited version"}
        </button>
        {renderM.isError && <p className="text-[11.5px] text-[#ffb3b4]">{(renderM.error as Error).message}</p>}
        <button type="button" className="pill-btn h-9 text-[13px] text-ink-2 hover:text-ink" disabled={acceptedEditIds.length === 0 && customCuts.length === 0} onClick={exportPlan}>
          <IconDownload className="size-4" />
          Export edit list (JSON)
        </button>
      </div>
    </div>
  );
}
