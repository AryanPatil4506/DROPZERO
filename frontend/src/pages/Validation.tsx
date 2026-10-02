import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useValidation } from "../api/hooks";
import type { Detection, Metrics, Validation } from "../api/types";
import { ErrorBox, MockBadge, Segmented, Spinner } from "../components/ui";
import { mmss, pct } from "../lib/format";

type MetricKey = keyof Metrics;
const METRICS: { key: MetricKey; label: string; better: "lower" | "higher"; hint: string }[] = [
  { key: "mae", label: "MAE", better: "lower", hint: "Mean absolute error of the retention curve" },
  { key: "rmse", label: "RMSE", better: "lower", hint: "Root-mean-square error of the curve" },
  { key: "pearson", label: "Pearson", better: "higher", hint: "Linear correlation with the actual curve" },
  { key: "spearman", label: "Spearman", better: "higher", hint: "Rank correlation with the actual curve" },
  {
    key: "hazard_spearman_pooled",
    label: "Drop ranking (pooled)",
    better: "higher",
    hint: "Does the model rank which segments lose the most viewers? Spearman of per-segment drop rate, all test videos pooled",
  },
  {
    key: "hazard_spearman_within_video_mean",
    label: "Drop ranking (within video)",
    better: "higher",
    hint: "Same ranking check, computed inside each video and averaged",
  },
];

function MetricCard({ m, data }: { m: (typeof METRICS)[number]; data: Validation }) {
  const ours = data.metrics[m.key];
  const base = data.baseline[m.key];
  if (ours == null || base == null) return null;
  const better = m.better === "lower" ? ours < base : ours > base;
  return (
    <div className={`glass rounded-[24px] p-5 ${better ? "" : "border-high/40"}`} title={m.hint}>
      <p className="eyebrow">{m.label} · {m.better} is better</p>
      <p className="mt-3 text-[30px] leading-none font-medium tracking-tight tabular-nums">{ours.toFixed(3)}</p>
      <p className="mt-3 flex items-center justify-between gap-3 text-xs text-ink-2">
        <span className="truncate">Baseline</span>
        <span className="text-ink tabular-nums">{base.toFixed(3)}</span>
      </p>
      <p className={`mt-2 text-xs ${better ? "text-[#7fd8b8]" : "text-[#ffb3b4]"}`}>{better ? "Beats the baseline" : "Does not beat the baseline"}</p>
    </div>
  );
}

function DetectionRow({ label, d }: { label: string; d: Detection }) {
  return (
    <tr className="border-b border-line last:border-0">
      <td className="py-2.5 pr-4 text-ink">{label}</td>
      <td className="px-3 tabular-nums">{d.precision.toFixed(2)}</td>
      <td className="px-3 tabular-nums">{d.recall.toFixed(2)}</td>
      <td className="px-3 tabular-nums">{d.f1.toFixed(2)}</td>
      <td className="px-3 tabular-nums">
        {d.detected} / {d.total}
      </td>
      <td className="px-3 tabular-nums">{d.predicted ?? "—"}</td>
      <td className="pl-3 tabular-nums">{d.median_delay_s == null ? "—" : `${d.median_delay_s.toFixed(1)} s`}</td>
    </tr>
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
    const pts = example?.actual ?? [];
    const after = pts.findIndex((p) => p.t >= t);
    if (after <= 0) return pts[Math.max(after, 0)]?.retention ?? 0;
    const a = pts[after - 1];
    const b = pts[after];
    return a.retention + ((t - a.t) / (b.t - a.t || 1)) * (b.retention - a.retention);
  };

  if (v.isPending) return <div className="p-8"><Spinner label="Loading validation" /></div>;
  if (v.isError) return <div className="p-8"><ErrorBox error={v.error} title="Couldn't load validation results" /></div>;
  const d = v.data;
  const missed = d.detection.total - d.detection.detected;
  const ablations = Object.entries(d.ablations ?? {});

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 p-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Model performance</p>
          <h1 className="mt-1 text-[28px] font-medium tracking-tight">Validation against real viewing data</h1>
          <p className="mt-2 max-w-3xl text-sm text-ink-2">{d.dataset}</p>
          <p className="mt-1 text-xs text-ink-3">
            {d.n_videos_train != null && `${d.n_videos_train} training videos · `}
            {d.n_videos_test} test videos · {d.split} · model {d.model_version}
          </p>
        </div>
        <MockBadge note={d._mock} />
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Curve accuracy">
        {METRICS.map((m) => (
          <MetricCard key={m.key} m={m} data={d} />
        ))}
      </section>
      <p className="-mt-2 px-1 text-xs text-ink-3">Baseline: {d.baseline.name}.</p>

      <section className="glass grid gap-6 rounded-[28px] p-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)]" aria-label="Drop detection">
        <div>
          <p className="eyebrow">Major drop detection · ±{d.detection.tolerance_s} s tolerance</p>
          <p className="mt-3 text-[32px] leading-tight font-medium tracking-tight">
            {d.detection.detected} of {d.detection.total} major drops detected
          </p>
          <p className="mt-2 text-sm text-[#ffb3b4]">{missed} missed. Misses are shown, not hidden.</p>
          {d.detection.predicted != null && (
            <p className="mt-1 text-sm text-ink-2">
              {d.detection.predicted} drops predicted in total, so precision is {d.detection.precision.toFixed(2)}.
            </p>
          )}
          {d.band && (
            <p className="mt-4 text-sm text-ink-2">
              Confidence band ({Math.round(d.band.quantiles[0] * 100)}–{Math.round(d.band.quantiles[d.band.quantiles.length - 1] * 100)}th
              percentile) contains the actual curve <span className="text-ink">{pct(d.band.test_coverage, 1)}</span> of the time on test videos.
            </p>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-ink-2">
            <thead className="text-xs text-ink-3">
              <tr className="border-b border-line">
                <th className="py-2 pr-4 font-medium" />
                <th className="px-3 font-medium">Precision</th>
                <th className="px-3 font-medium">Recall</th>
                <th className="px-3 font-medium">F1</th>
                <th className="px-3 font-medium">Detected</th>
                <th className="px-3 font-medium">Predicted</th>
                <th className="pl-3 font-medium">Median delay</th>
              </tr>
            </thead>
            <tbody>
              <DetectionRow label="DROPZERO model" d={d.detection} />
              {d.baseline_detection && <DetectionRow label="Baseline" d={d.baseline_detection} />}
            </tbody>
          </table>
        </div>
      </section>

      {ablations.length > 0 && (
        <section className="glass rounded-[28px] p-6" aria-label="Ablations">
          <h2 className="text-[17px] font-medium">Ablations: model trained without one feature group</h2>
          <p className="mt-1 text-xs text-ink-3">Compare with the full model above. Worse numbers mean the removed group was helping.</p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm text-ink-2">
              <thead className="text-xs text-ink-3">
                <tr className="border-b border-line">
                  <th className="py-2 pr-4 font-medium">Without</th>
                  <th className="px-3 font-medium">MAE (lower is better)</th>
                  <th className="px-3 font-medium">Drop ranking, pooled</th>
                  <th className="pl-3 font-medium">Detection F1</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-line text-ink">
                  <td className="py-2.5 pr-4">Nothing (full model)</td>
                  <td className="px-3 tabular-nums">{d.metrics.mae.toFixed(3)}</td>
                  <td className="px-3 tabular-nums">{d.metrics.hazard_spearman_pooled?.toFixed(3) ?? "—"}</td>
                  <td className="pl-3 tabular-nums">{d.detection.f1.toFixed(3)}</td>
                </tr>
                {ablations.map(([group, a]) => (
                  <tr key={group} className="border-b border-line last:border-0">
                    <td className="py-2.5 pr-4 capitalize">{group}</td>
                    <td className="px-3 tabular-nums">{a.mae.toFixed(3)}</td>
                    <td className="px-3 tabular-nums">{a.hazard_spearman_pooled.toFixed(3)}</td>
                    <td className="pl-3 tabular-nums">{a.detection_f1.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

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
                options={d.examples.map((_, i) => ({ value: String(i), label: `#${i + 1}` }))}
              />
            )}
          </div>
          <div className="mt-4 h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 18, right: 20, bottom: 0, left: 0 }}>
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
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 flex gap-4 text-xs text-ink-2">
            <span className="inline-flex items-center gap-1.5"><i className="size-2.5 rounded-full bg-ok" />Detected ({example.drops.filter((x) => x.detected).length})</span>
            <span className="inline-flex items-center gap-1.5"><i className="size-2.5 rounded-full bg-high" />Missed ({example.drops.filter((x) => !x.detected).length})</span>
          </p>
        </section>
      )}
    </div>
  );
}
