import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useValidation } from "../api/hooks";
import type { Metrics, Validation } from "../api/types";
import { ErrorBox, MockBadge, Segmented, Spinner } from "../components/ui";
import { mmss, pct } from "../lib/format";

const METRICS: { key: keyof Metrics; label: string; better: "lower" | "higher"; hint: string }[] = [
  { key: "mae", label: "MAE", better: "lower", hint: "Mean absolute error of the curve" },
  { key: "rmse", label: "RMSE", better: "lower", hint: "Root-mean-square error of the curve" },
  { key: "pearson", label: "Pearson", better: "higher", hint: "Linear correlation with actual" },
  { key: "spearman", label: "Spearman", better: "higher", hint: "Rank correlation with actual" },
];

function MetricCard({ m, data }: { m: (typeof METRICS)[number]; data: Validation }) {
  const ours = data.metrics[m.key];
  const base = data.baseline[m.key];
  const better = m.better === "lower" ? ours < base : ours > base;
  return (
    <div className="glass rounded-[24px] p-5" title={m.hint}>
      <p className="eyebrow">{m.label} · {m.better} is better</p>
      <p className="mt-3 text-[32px] leading-none font-medium tracking-tight tabular-nums">{ours.toFixed(3)}</p>
      <p className="mt-3 flex items-center justify-between text-xs text-ink-2">
        <span>{data.baseline.name}</span>
        <span className="tabular-nums text-ink">{base.toFixed(3)}</span>
      </p>
      <p className={`mt-2 text-xs ${better ? "text-[#7fd8b8]" : "text-[#ffb3b4]"}`}>{better ? "Beats the baseline" : "Does not beat the baseline"}</p>
    </div>
  );
}

function OverlayTooltip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: number }) {
  if (!active || !payload?.length || label == null) return null;
  return (
    <div className="glass rounded-xl px-3 py-2 text-xs">
      <p className="font-medium tabular-nums">{mmss(label)}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="mt-1 flex justify-between gap-4 text-ink-2">
          {p.dataKey === "actual" ? "Actual" : "Predicted"}
          <span className="text-ink tabular-nums">{pct(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

export default function ValidationPage() {
  const v = useValidation();
  const [exampleIdx, setExampleIdx] = useState(0);
  const example = v.data?.examples[exampleIdx];

  const rows = useMemo(() => {
    if (!example) return [];
    const map = new Map<number, { t: number; actual?: number; predicted?: number }>();
    for (const p of example.actual) map.set(p.t, { ...map.get(p.t), t: p.t, actual: p.retention });
    for (const p of example.predicted) map.set(p.t, { ...map.get(p.t), t: p.t, predicted: p.retention });
    return [...map.values()].sort((a, b) => a.t - b.t);
  }, [example]);
  const actualAt = (t: number) => {
    const exact = example?.actual.find((p) => p.t === t);
    if (exact) return exact.retention;
    const after = example?.actual.find((p) => p.t >= t);
    return after?.retention ?? 0;
  };

  if (v.isPending) return <div className="p-8"><Spinner label="Loading validation" /></div>;
  if (v.isError) return <div className="p-8"><ErrorBox error={v.error} title="Couldn't load validation results" /></div>;
  const d = v.data;
  const missed = d.detection.total - d.detection.detected;

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 p-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Model performance</p>
          <h1 className="mt-1 text-[28px] font-medium tracking-tight">Validation against real viewing data</h1>
          <p className="mt-2 max-w-3xl text-sm text-ink-2">{d.dataset}</p>
          <p className="mt-1 text-xs text-ink-3">
            {d.n_videos_test} test videos · {d.split} · model {d.model_version}
          </p>
        </div>
        <MockBadge note={d._mock} />
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Curve accuracy">
        {METRICS.map((m) => (
          <MetricCard key={m.key} m={m} data={d} />
        ))}
      </section>

      <section className="glass grid gap-5 rounded-[28px] p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]" aria-label="Drop detection">
        <div>
          <p className="eyebrow">Major drop detection · ±{d.detection.tolerance_s} s tolerance</p>
          <p className="mt-3 text-[34px] leading-tight font-medium tracking-tight">
            {d.detection.detected} of {d.detection.total} major drops detected
          </p>
          <p className="mt-2 text-sm text-[#ffb3b4]">{missed} missed. Misses are listed in the examples, not hidden.</p>
        </div>
        <div className="grid grid-cols-3 gap-3 self-center">
          {(["precision", "recall", "f1"] as const).map((k) => (
            <div key={k} className="rounded-2xl bg-white/[0.05] p-4">
              <p className="text-[26px] font-medium tabular-nums">{d.detection[k].toFixed(2)}</p>
              <p className="mt-1 text-xs text-ink-2">{k === "f1" ? "F1" : k[0].toUpperCase() + k.slice(1)}</p>
            </div>
          ))}
        </div>
      </section>

      {example && (
        <section className="glass rounded-[28px] p-6" aria-label="Example overlay">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-[17px] font-medium">Actual vs predicted · {example.title}</h2>
              <p className="text-xs text-ink-3">Held-out example. Drops marked detected (green) or missed (red).</p>
            </div>
            {d.examples.length > 1 && (
              <Segmented
                label="Example video"
                value={String(exampleIdx)}
                onChange={(val) => setExampleIdx(Number(val))}
                options={d.examples.map((e, i) => ({ value: String(i), label: e.title }))}
              />
            )}
          </div>
          <div className="mt-4 h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={mmss} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(x: number) => `${Math.round(x * 100)}%`} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={46} />
                <Tooltip content={<OverlayTooltip />} cursor={{ stroke: "rgba(255,255,255,0.25)" }} />
                <Legend verticalAlign="top" align="left" height={30} formatter={(val: string) => <span className="text-xs text-ink-2">{val === "actual" ? "Actual (solid)" : "Predicted (dashed)"}</span>} />
                <Line dataKey="actual" stroke="var(--color-actual)" strokeWidth={2.25} dot={false} connectNulls isAnimationActive={false} />
                <Line dataKey="predicted" stroke="var(--color-pred)" strokeWidth={2} strokeDasharray="6 5" dot={false} connectNulls isAnimationActive={false} />
                {example.drops.map((drop) => (
                  <ReferenceDot
                    key={drop.t}
                    x={drop.t}
                    y={actualAt(drop.t)}
                    r={6}
                    fill={drop.detected ? "var(--color-ok)" : "var(--color-high)"}
                    stroke="var(--color-panel)"
                    strokeWidth={2}
                    label={{ value: drop.detected ? "Detected" : "Missed", position: "top", fill: "var(--color-ink-2)", fontSize: 11 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
    </div>
  );
}
