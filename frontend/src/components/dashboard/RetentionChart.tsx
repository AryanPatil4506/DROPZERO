import { useMemo, type MouseEvent } from "react";
import { Area, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Flag, Prediction, Risk } from "../../api/types";
import { mmss, pct } from "../../lib/format";
import { useTimeline } from "./timeline-context";

/** Plot-area insets shared with the tracks below so everything lines up on one time axis. */
export const PLOT_LEFT = 46;
export const PLOT_RIGHT = 18;

interface Row {
  t: number;
  retention: number;
  band: [number, number];
  risk: Risk | null;
  flag: Flag | null;
}

const RISK_COLOR: Record<string, string> = { high: "var(--color-high)", medium: "var(--color-med)" };

function riskAt(prediction: Prediction, t: number): Risk | null {
  // Each point sits at a segment's end; the drop it shows belongs to that segment.
  const seg = prediction.segments.find((s) => Math.abs(s.end - t) < 0.01);
  return seg ? seg.risk : null;
}

function TooltipBody({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="glass min-w-48 rounded-xl px-3 py-2 text-xs">
      <p className="font-medium text-ink tabular-nums">{mmss(row.t)}</p>
      <p className="mt-1 flex justify-between gap-4 text-ink-2">
        Predicted retention <span className="text-ink tabular-nums">{pct(row.retention)}</span>
      </p>
      <p className="flex justify-between gap-4 text-ink-2">
        Range <span className="text-ink tabular-nums">{`${pct(row.band[0])}–${pct(row.band[1])}`}</span>
      </p>
      {row.risk && row.risk !== "low" && (
        <p className="mt-1 flex items-center gap-1.5 text-ink">
          <span className="size-2 rounded-full" style={{ background: RISK_COLOR[row.risk] }} />
          {row.risk === "high" ? "High risk" : "Medium risk"}
        </p>
      )}
      {row.flag && <p className="mt-1 max-w-60 text-ink-2">{row.flag.title}</p>}
    </div>
  );
}

export default function RetentionChart({
  prediction,
  flags,
  height = 168,
  onPickFlag,
}: {
  prediction: Prediction;
  flags: Flag[];
  height?: number;
  onPickFlag: (flag: Flag | null, t: number) => void;
}) {
  const { time, seek, view, cut, selectedFlagId, skipRanges, previewEdited } = useTimeline();
  const flagAt = (t: number) => flags.find((f) => t > f.start && t <= f.end + 0.01) ?? null;

  const rows: Row[] = useMemo(
    () =>
      prediction.points.map((p) => ({
        t: p.t,
        retention: p.retention,
        band: [p.lower, p.upper],
        risk: riskAt(prediction, p.t),
        flag: flags.find((f) => p.t > f.start && p.t <= f.end + 0.01) ?? null,
      })),
    [prediction, flags],
  );
  const selected = flags.find((f) => f.id === selectedFlagId) ?? null;

  // Click anywhere on the plot: map the pointer to a time, seek there and select its flag.
  const onClick = (e: MouseEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - box.left - PLOT_LEFT;
    const w = box.width - PLOT_LEFT - PLOT_RIGHT;
    if (x < 0 || x > w) return;
    const t = view.start + (x / w) * (view.end - view.start);
    seek(t);
    onPickFlag(flagAt(t), t);
  };

  return (
    <div className="relative cursor-crosshair" style={{ height }} onClick={onClick}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: PLOT_RIGHT, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="band-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="var(--color-pred)" stopOpacity={0.28} />
              <stop offset="1" stopColor="var(--color-pred)" stopOpacity={0.08} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="t"
            type="number"
            domain={[view.start, view.end]}
            allowDataOverflow
            tickFormatter={mmss}
            tick={{ fill: "var(--color-ink-3)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickCount={7}
            height={22}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fill: "var(--color-ink-3)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={PLOT_LEFT}
          />
          {[0.25, 0.5, 0.75].map((y) => (
            <ReferenceLine key={y} y={y} stroke="rgba(255,255,255,0.06)" />
          ))}
          {selected && (
            <ReferenceArea
              x1={selected.start}
              x2={selected.end}
              fill={RISK_COLOR[selected.severity]}
              fillOpacity={0.13}
              stroke={RISK_COLOR[selected.severity]}
              strokeOpacity={0.5}
            />
          )}
          {previewEdited &&
            skipRanges.map((r) => (
              <ReferenceArea key={`skip-${r.start}`} x1={r.start} x2={r.end} fill="var(--color-accent)" fillOpacity={0.1} stroke="none" />
            ))}
          {cut && (
            <ReferenceArea x1={cut.start} x2={cut.end} fill="var(--color-accent)" fillOpacity={0.22} stroke="var(--color-accent)" strokeWidth={1.5} />
          )}
          <Area dataKey="band" stroke="none" fill="url(#band-fill)" isAnimationActive={false} activeDot={false} />
          <Line
            dataKey="retention"
            stroke="var(--color-pred)"
            strokeWidth={2.25}
            isAnimationActive={false}
            activeDot={{ r: 4, fill: "var(--color-pred)", stroke: "var(--color-panel)", strokeWidth: 2 }}
            dot={(props: { cx?: number; cy?: number; index?: number; payload?: Row }) => {
              const { cx, cy, payload, index } = props;
              if (cx == null || cy == null || !payload?.risk || payload.risk === "low") return <g key={`d${index}`} />;
              const isSel = !!payload.flag && payload.flag.id === selectedFlagId;
              return (
                <g key={`d${index}`}>
                  {isSel && <circle cx={cx} cy={cy} r={10} fill={RISK_COLOR[payload.risk]} opacity={0.25} />}
                  <circle cx={cx} cy={cy} r={5.5} fill={RISK_COLOR[payload.risk]} stroke="var(--color-panel)" strokeWidth={2} />
                </g>
              );
            }}
          />
          <ReferenceLine x={time} stroke="var(--color-accent)" strokeWidth={1.5} ifOverflow="hidden" />
          <Tooltip content={<TooltipBody />} cursor={{ stroke: "rgba(255,255,255,0.25)" }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
