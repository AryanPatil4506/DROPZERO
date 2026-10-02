import type { ComponentType, SVGProps } from "react";
import { useNavigate } from "react-router-dom";
import type { Action, Edit, Evidence, Flag } from "../../api/types";
import { ACTION_LABEL, editSentence, evidenceValue, FLAG_CATEGORY_LABEL, mmss, range, SOURCE_HINT, SOURCE_LABEL } from "../../lib/format";
import { IconHook, IconKeep, IconMove, IconRewrite, IconScissors, IconShorten, IconVisual } from "../icons";
import { SeverityTag } from "../ui";
import { useTimeline } from "./timeline-context";

const ACTION_ICON: Record<Action, ComponentType<SVGProps<SVGSVGElement>>> = {
  CUT: IconScissors,
  MOVE: IconMove,
  SHORTEN: IconShorten,
  REWRITE: IconRewrite,
  ADD_HOOK: IconHook,
  ADD_VISUAL: IconVisual,
  KEEP: IconKeep,
};
const ACTION_GRID: Action[] = ["CUT", "MOVE", "SHORTEN", "REWRITE", "ADD_HOOK", "ADD_VISUAL"];

/** Evidence row styled like the reference's slider pills; 0–1 ratios get a proportional fill. */
function EvidenceRow({ ev }: { ev: Evidence }) {
  const { seek } = useTimeline();
  const ratio = typeof ev.value === "number" && !ev.unit && ev.value >= 0 && ev.value <= 1 ? ev.value : null;
  return (
    <li className="relative overflow-hidden rounded-full bg-white/[0.06]">
      {ratio != null && (
        <span className="absolute inset-y-0 left-0 rounded-full bg-white/[0.14] shadow-[inset_-2px_0_0_rgba(255,255,255,0.55)]" style={{ width: `${ratio * 100}%` }} aria-hidden />
      )}
      <div className="relative flex min-h-10 items-center justify-between gap-3 px-4 py-2 text-[13px]">
        <span className="text-ink">{ev.label}</span>
        <span className="shrink-0 font-medium text-ink tabular-nums">{evidenceValue(ev.value, ev.unit)}</span>
      </div>
      {ev.ref_start != null && ev.ref_end != null && (
        <button
          type="button"
          onClick={() => seek(ev.ref_start!)}
          className="relative mb-2 ml-4 text-xs text-accent underline-offset-2 hover:underline"
        >
          matches {range(ev.ref_start, ev.ref_end)}
        </button>
      )}
    </li>
  );
}

function EditCard({ edit }: { edit: Edit }) {
  return (
    <li className="rounded-2xl bg-white/[0.05] px-4 py-3 text-[13px]">
      <p className="font-medium text-ink">
        {editSentence(edit.action, edit.start, edit.end, edit.target_time)}
        <span className="text-ink-2">: {edit.reason}</span>
      </p>
      {edit.rewrite_text && <p className="mt-2 rounded-xl bg-black/30 px-3 py-2 text-ink-2">“{edit.rewrite_text}”</p>}
    </li>
  );
}

export default function RiskDrawer({
  projectId,
  flag,
  edits,
  flagCount,
  unavailable = false,
}: {
  projectId: string;
  flag: Flag | null;
  edits: Edit[];
  flagCount: number;
  unavailable?: boolean;
}) {
  const navigate = useNavigate();
  const { cut, setCut, seek, acceptedEditIds, setAcceptedEditIds } = useTimeline();

  if (!flag) {
    return (
      <section className="glass rounded-[26px] p-5" aria-label="Risk details">
        <p className="eyebrow">Why would I leave?</p>
        <p className="mt-3 text-[15px] text-ink">
          {unavailable
            ? "Flags aren't available for this project yet."
            : flagCount > 0
              ? "Click a red or yellow point on the curve, a coloured segment, or a flag to see the evidence."
              : "No flagged ranges for this project."}
        </p>
      </section>
    );
  }

  const flagEdits = edits.filter((e) => flag.edit_ids.includes(e.id));
  const simIds = flagEdits.filter((e) => e.simulatable !== false).map((e) => e.id);
  const cutEdit = flagEdits.find((e) => e.action === "CUT" || e.action === "SHORTEN") ?? flagEdits[0];
  const showingCut = !!cut && !!cutEdit && cut.start === cutEdit.start && cut.end === cutEdit.end;
  const activeActions = new Set(flagEdits.map((e) => e.action));

  return (
    <section className="glass rounded-[26px] p-5" aria-label="Risk details" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2">
          <SeverityTag severity={flag.severity} />
          {flag.source && (
            <span className={`chip h-5 text-[10.5px] ${flag.source === "rule" ? "" : "border-pred/50 text-[#a9c0f2]"}`} title={SOURCE_HINT[flag.source]}>
              {SOURCE_LABEL[flag.source] ?? flag.source}
            </span>
          )}
        </span>
        <button type="button" onClick={() => seek(flag.start)} className="text-[13px] text-ink-2 tabular-nums hover:text-ink">
          {mmss(flag.start)} – {mmss(flag.end)}
        </button>
      </div>
      <p className="mt-4 eyebrow">Why would I leave? · {FLAG_CATEGORY_LABEL[flag.category] ?? flag.category}</p>
      <h2 className="mt-1.5 text-[19px] leading-snug font-medium tracking-tight">{flag.title}</h2>
      <p className="mt-2 text-[14px] text-ink-2">{flag.explanation}</p>

      <ul className="mt-4 space-y-2" aria-label="Evidence">
        {flag.evidence.map((ev, i) => (
          <EvidenceRow key={i} ev={ev} />
        ))}
      </ul>

      {flag.secondary_categories.length > 0 && (
        <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
          Also:
          {flag.secondary_categories.map((c) => (
            <span key={c} className="chip">
              {FLAG_CATEGORY_LABEL[c] ?? c}
            </span>
          ))}
        </p>
      )}

      <div className="mt-5 rounded-[22px] bg-black/25 p-3">
        <div className="flex items-baseline justify-between px-1">
          <p className="text-[15px] font-medium">Suggested edit</p>
          <p className="text-xs text-ink-3">{flagEdits.length ? "from measured evidence" : "none"}</p>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2" aria-label="Edit actions">
          {ACTION_GRID.map((a) => {
            const Icon = ACTION_ICON[a];
            const on = activeActions.has(a);
            return (
              <span
                key={a}
                title={ACTION_LABEL[a]}
                className={`flex h-12 flex-col items-center justify-center gap-0.5 rounded-2xl text-[10px] font-medium ${
                  on ? "bg-accent text-[#160700]" : "bg-white/[0.05] text-ink-3"
                }`}
              >
                <Icon className="size-4" />
                {ACTION_LABEL[a]}
              </span>
            );
          })}
        </div>
        <ul className="mt-3 space-y-2">
          {flagEdits.map((e) => (
            <EditCard key={e.id} edit={e} />
          ))}
        </ul>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {cutEdit && (
          <button
            type="button"
            className="pill-ghost"
            aria-pressed={showingCut}
            onClick={() => {
              if (showingCut) setCut(null);
              else {
                setCut({ start: cutEdit.start, end: cutEdit.end });
                seek(cutEdit.start);
              }
            }}
          >
            {showingCut ? "Hide cut" : "Show me what to cut"}
          </button>
        )}
        {flagEdits.length > 0 && (
          <button
            type="button"
            className="pill-ghost"
            aria-pressed={flagEdits.every((e) => acceptedEditIds.includes(e.id))}
            onClick={() => {
              const ids = flagEdits.map((e) => e.id);
              const all = ids.every((i) => acceptedEditIds.includes(i));
              setAcceptedEditIds(all ? acceptedEditIds.filter((i) => !ids.includes(i)) : [...new Set([...acceptedEditIds, ...ids])]);
            }}
          >
            {flagEdits.every((e) => acceptedEditIds.includes(e.id)) ? "In edit plan ✓" : "Add to edit plan"}
          </button>
        )}
        <button
          type="button"
          className="pill-accent"
          disabled={simIds.length === 0}
          title={simIds.length === 0 ? (flagEdits.length ? "This edit is advice only; it can't be simulated" : "No edit to simulate") : undefined}
          onClick={() => navigate(`/projects/${projectId}/simulate?edits=${simIds.join(",")}`)}
        >
          Simulate fix
        </button>
      </div>
    </section>
  );
}
