import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Edit, Project } from "../../api/types";
import { ACTION_LABEL, editSentence, mmss, range } from "../../lib/format";
import { IconClose, IconDownload } from "../icons";
import { useTimeline } from "./timeline-context";

const SKIPPABLE = new Set(["CUT", "SHORTEN"]);

/**
 * The edit decision list: accept suggested edits, mark your own cuts, preview playback with the
 * cuts skipped, simulate, or export. Nothing here touches the original video file.
 */
export default function EditPlan({ project, edits }: { project: Project; edits: Edit[] }) {
  const navigate = useNavigate();
  const { time, seek, acceptedEditIds, toggleEdit, setAcceptedEditIds, customCuts, addCustomCut, removeCustomCut, previewEdited, setPreviewEdited, skipRanges } =
    useTimeline();
  const [markIn, setMarkIn] = useState<number | null>(null);
  const simulatableAccepted = edits.filter((e) => acceptedEditIds.includes(e.id) && e.simulatable !== false).map((e) => e.id);

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
        ...customCuts.map((c) => ({ source: "custom", id: c.id, action: "CUT", start: c.start, end: c.end, target_time: null, reason: "Marked by creator" })),
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
    <div className="grid h-full min-h-0 gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
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
              <span className="font-medium text-ink">Cut {range(c.start, c.end)}</span>
              <span className="block text-ink-2">Marked by you · not simulated yet</span>
            </button>
            <button type="button" aria-label={`Remove cut ${range(c.start, c.end)}`} onClick={() => removeCustomCut(c.id)} className="grid size-7 place-items-center rounded-full text-ink-3 hover:bg-white/10 hover:text-ink">
              <IconClose className="size-4" />
            </button>
          </li>
        ))}
        {edits.length === 0 && customCuts.length === 0 && <li className="px-1 text-sm text-ink-3">No edits yet. Mark a cut at the playhead to start a plan.</li>}
      </ul>

      <div className="flex flex-col gap-2">
        <div className="flex gap-2">
          <button type="button" className="pill-ghost h-9 flex-1 px-3 text-[13px]" onClick={() => setMarkIn(time)}>
            Mark in {markIn != null && <span className="text-accent tabular-nums">{mmss(markIn)}</span>}
          </button>
          <button
            type="button"
            className="pill-ghost h-9 flex-1 px-3 text-[13px]"
            disabled={markIn == null || time - markIn < 0.5}
            title={markIn == null ? "Mark in first" : "Ends the cut at the playhead"}
            onClick={() => {
              if (markIn == null) return;
              addCustomCut({ start: markIn, end: time });
              setMarkIn(null);
            }}
          >
            Mark out
          </button>
        </div>
        <button type="button" className="pill-ghost h-9 text-[13px]" onClick={() => setAcceptedEditIds(acceptedEditIds.length === edits.length ? [] : edits.map((e) => e.id))} disabled={edits.length === 0}>
          {acceptedEditIds.length === edits.length && edits.length > 0 ? "Clear accepted" : "Accept all suggestions"}
        </button>
        <button type="button" className={`pill-btn h-9 text-[13px] ${previewEdited ? "bg-accent text-[#160700]" : "border border-line-2 bg-white/5 text-ink hover:bg-white/10"}`} disabled={skipRanges.length === 0} onClick={() => setPreviewEdited(!previewEdited)} aria-pressed={previewEdited}>
          {previewEdited ? "Previewing with cuts" : "Preview with cuts"}
        </button>
        <button type="button" className="pill-accent h-9 text-[13px]" disabled={simulatableAccepted.length === 0} onClick={() => navigate(`/projects/${project.id}/simulate?edits=${simulatableAccepted.join(",")}`)}>
          Simulate accepted edits
        </button>
        <button type="button" className="pill-btn h-9 text-[13px] text-ink-2 hover:text-ink" disabled={acceptedEditIds.length === 0 && customCuts.length === 0} onClick={exportPlan}>
          <IconDownload className="size-4" />
          Export edit list (JSON)
        </button>
      </div>
    </div>
  );
}
