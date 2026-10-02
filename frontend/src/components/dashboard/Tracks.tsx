import type { ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useScores } from "../../api/hooks";
import type { SegmentScore } from "../../api/types";
import type { Edit, Flag, Prediction, Segment, Topic } from "../../api/types";
import { ACTION_LABEL, mmss, range } from "../../lib/format";
import { PLOT_LEFT, PLOT_RIGHT } from "./RetentionChart";
import { overlaps, useTimeline, type TimeRange } from "./timeline-context";

const RISK_BG: Record<string, string> = {
  high: "bg-high/80 hover:bg-high",
  medium: "bg-med/80 hover:bg-med",
  low: "bg-white/10 hover:bg-white/20",
};

function useX() {
  const { view } = useTimeline();
  const span = view.end - view.start || 1;
  return (r: TimeRange) => {
    const left = ((Math.max(r.start, view.start) - view.start) / span) * 100;
    const right = ((Math.min(r.end, view.end) - view.start) / span) * 100;
    return { left: `${left}%`, width: `${Math.max(0, right - left)}%`, visible: r.end > view.start && r.start < view.end };
  };
}

function Lane({ label, children, thin = false }: { label: string; children: ReactNode; thin?: boolean }) {
  return (
    <div className={`relative flex items-center ${thin ? "h-[11px]" : "h-[22px]"}`}>
      <span className={`absolute left-0 w-[46px] pr-2 text-right font-medium tracking-wide text-ink-3 uppercase ${thin ? "text-[8.5px] leading-none" : "text-[10px]"}`}>{label}</span>
      <div className="relative h-full flex-1" style={{ marginLeft: PLOT_LEFT, marginRight: PLOT_RIGHT }}>
        {children}
      </div>
    </div>
  );
}

/** Segment bar (coloured by risk), topic sections and suggested edits, all on the curve's time axis. */
export default function Tracks({
  segments,
  prediction,
  topics,
  flags,
  edits,
  onPickFlag,
  lanes = "structure",
}: {
  lanes?: "structure" | "scores";
  segments: Segment[];
  prediction: Prediction | null;
  topics: Topic[];
  flags: Flag[];
  edits: Edit[];
  onPickFlag: (flag: Flag | null, t: number) => void;
}) {
  const { seek, time, view, cut, selectedFlagId, acceptedEditIds, customCuts } = useTimeline();
  const x = useX();
  const { id = "" } = useParams();
  const scoreData = useScores(id).data;
  const scores = lanes === "scores" ? scoreData : undefined;
  const scoreBg = (v: number | null) =>
    v == null ? "bg-white/[0.04]" : v >= 65 ? "bg-ok/70" : v >= 40 ? "bg-med/70" : "bg-high/70";
  const LANES: [string, keyof SegmentScore][] = [["Pace", "pacing"], ["Content", "content"], ["Visual", "visual"], ["Audio", "audio"]];
  const riskOf = (i: number) => prediction?.segments.find((s) => s.index === i)?.risk ?? "low";
  const playhead = ((time - view.start) / (view.end - view.start || 1)) * 100;

  return (
    <div className="relative space-y-1">
      <Lane label="Risk">
        {segments.map((s) => {
          const pos = x(s);
          if (!pos.visible) return null;
          const risk = riskOf(s.index);
          const flag = flags.find((f) => overlaps(f, s)) ?? null;
          const isSel = !!flag && flag.id === selectedFlagId;
          return (
            <button
              key={s.id}
              type="button"
              title={`${range(s.start, s.end)} · ${risk} risk${s.kind === "silence" ? " · silence" : ""}`}
              aria-label={`Segment ${range(s.start, s.end)}, ${risk} risk`}
              onClick={() => {
                seek(s.start);
                onPickFlag(flag, s.start);
              }}
              className={`absolute top-0.5 bottom-0.5 rounded-[5px] border-r-2 border-panel transition-colors ${RISK_BG[risk]} ${
                isSel ? "ring-2 ring-ink ring-offset-0" : ""
              } ${s.kind === "silence" ? "opacity-50" : ""}`}
              style={{ left: pos.left, width: pos.width }}
            />
          );
        })}
        {cut && x(cut).visible && (
          <span
            className="pointer-events-none absolute -top-0.5 -bottom-0.5 rounded-md border-2 border-accent bg-accent/25"
            style={{ left: x(cut).left, width: x(cut).width }}
          />
        )}
      </Lane>

      {lanes === "structure" && (
        <>
      <Lane label="Topic">
        {topics.map((t, i) => {
          const pos = x(t);
          if (!pos.visible) return null;
          return (
            <button
              key={t.index}
              type="button"
              onClick={() => seek(t.start)}
              title={`${t.label ?? `Section ${i + 1}`} · ${range(t.start, t.end)}`}
              className="absolute top-0.5 bottom-0.5 overflow-hidden rounded-[5px] border-r-2 border-panel bg-pred/25 px-2 text-left text-[11px] whitespace-nowrap text-ink-2 hover:bg-pred/40"
              style={{ left: pos.left, width: pos.width }}
            >
              {t.label ?? `Section ${i + 1}`}
            </button>
          );
        })}
      </Lane>

      <Lane label="Edits">
        {edits.map((e) => {
          const pos = x(e);
          if (!pos.visible) return null;
          const active = !!cut && Math.abs(cut.start - e.start) < 0.01 && Math.abs(cut.end - e.end) < 0.01;
          const accepted = acceptedEditIds.includes(e.id);
          return (
            <button
              key={e.id}
              type="button"
              onClick={() => {
                seek(e.start);
                onPickFlag(flags.find((f) => f.id === e.flag_id) ?? null, e.start);
              }}
              title={`${ACTION_LABEL[e.action]} ${range(e.start, e.end)}: ${e.reason}${accepted ? " (accepted)" : ""}`}
              className={`absolute top-1 bottom-1 overflow-hidden rounded-full px-2 text-left text-[10px] font-semibold whitespace-nowrap ${
                accepted || active ? "bg-accent text-[#160700]" : "border border-accent/70 bg-accent/10 text-accent hover:bg-accent/25"
              } ${active ? "ring-2 ring-ink" : ""}`}
              style={{ left: pos.left, width: pos.width, minWidth: 6 }}
            >
              {ACTION_LABEL[e.action].toUpperCase()}
            </button>
          );
        })}
        {customCuts.map((c) => {
          const pos = x(c);
          if (!pos.visible) return null;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => seek(c.start)}
              title={`Your cut ${range(c.start, c.end)}`}
              className="absolute top-1 bottom-1 overflow-hidden rounded-full border border-dashed border-accent bg-accent/30 px-2 text-left text-[10px] font-semibold whitespace-nowrap text-ink"
              style={{ left: pos.left, width: pos.width, minWidth: 6 }}
            >
              MY CUT
            </button>
          );
        })}
        {edits.length === 0 && customCuts.length === 0 && <span className="text-[11px] text-ink-3">No suggested edits</span>}
      </Lane>

        </>
      )}
      {scores && (
        <div className="space-y-[3px] pt-1" aria-label="Score lanes (DROPZERO internal scores)">
          {LANES.map(([label, key]) => (
            <Lane key={key} label={label} thin>
              {scores.segments.map((s) => {
                const pos = x(s);
                if (!pos.visible) return null;
                const v = s[key] as number | null;
                const inputs = Object.entries(s.inputs)
                  .filter(([, n]) => n != null)
                  .map(([k, n]) => `${k.replace(/_/g, " ")}: ${n}`)
                  .join("\n");
                return (
                  <button
                    key={`${key}-${s.index}`}
                    type="button"
                    title={`${label} ${v ?? "n/a"} · ${range(s.start, s.end)} · DROPZERO internal score\n${inputs}`}
                    onClick={() => seek(s.start)}
                    className={`absolute inset-y-0 rounded-[3px] border-r-2 border-panel ${scoreBg(v)}`}
                    style={{ left: pos.left, width: pos.width }}
                  />
                );
              })}
            </Lane>
          ))}
        </div>
      )}
      {/* playhead across the lanes */}
      {playhead >= 0 && playhead <= 100 && (
        <div className="pointer-events-none absolute inset-y-0" style={{ left: PLOT_LEFT, right: PLOT_RIGHT }}>
          <div className="absolute inset-y-0 w-px bg-accent" style={{ left: `${playhead}%` }}>
            <span className="sr-only">Playhead at {mmss(time)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
