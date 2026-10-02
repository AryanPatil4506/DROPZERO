import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFlags, useProject, useSimulation } from "../api/hooks";
import type { CurvePoint } from "../api/types";
import { IconChevron } from "../components/icons";
import { isNotFound } from "../api/errors";
import { EmptyState, ErrorBox, MockBadge, Spinner } from "../components/ui";
import { ACTION_LABEL, editSentence, mmss, pct } from "../lib/format";

interface Row {
  t: number;
  original?: number;
  simulated?: number;
}

/** Merge both curves onto one seconds axis; the simulated video is shorter (cut time removed). */
function mergeCurves(original: CurvePoint[], simulated: CurvePoint[]): Row[] {
  const rows = new Map<number, Row>();
  for (const p of original) rows.set(p.t, { ...rows.get(p.t), t: p.t, original: p.retention });
  for (const p of simulated) rows.set(p.t, { ...rows.get(p.t), t: p.t, simulated: p.retention });
  return [...rows.values()].sort((a, b) => a.t - b.t);
}

function SimTooltip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: number }) {
  if (!active || !payload?.length || label == null) return null;
  return (
    <div className="glass rounded-xl px-3 py-2 text-xs">
      <p className="font-medium tabular-nums">{mmss(label)} into each version</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="mt-1 flex items-center justify-between gap-4 text-ink-2">
          <span className="inline-flex items-center gap-1.5">
            <i className={`h-0.5 w-3 rounded ${p.dataKey === "original" ? "bg-orig" : "bg-sim"}`} />
            {p.dataKey === "original" ? "Original" : "Simulated"}
          </span>
          <span className="text-ink tabular-nums">{pct(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

export default function SimulatePage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const project = useProject(id);
  const flagsQ = useFlags(id);
  const edits = useMemo(() => flagsQ.data?.edits ?? [], [flagsQ.data]);

  const requested = params.get("edits");
  const selected = useMemo(
    () => (requested != null ? requested.split(",").filter(Boolean) : edits.filter((e) => e.simulatable !== false).map((e) => e.id)),
    [requested, edits],
  );
  const sim = useSimulation(id, selected);

  const toggle = (editId: string) => {
    const next = selected.includes(editId) ? selected.filter((x) => x !== editId) : [...selected, editId];
    setParams({ edits: next.join(",") }, { replace: true });
  };

  const rows = useMemo(() => (sim.data ? mergeCurves(sim.data.original, sim.data.simulated) : []), [sim.data]);

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-5">
      <nav className="flex items-center gap-2 text-sm text-ink-3">
        <Link to="/projects" className="hover:text-ink">Projects</Link>
        <IconChevron className="size-3.5" />
        <Link to={`/projects/${id}`} className="hover:text-ink">{project.data?.title ?? "Project"}</Link>
        <IconChevron className="size-3.5" />
        <span className="text-ink">Simulation</span>
      </nav>

      {/* the label is always visible and verbatim */}
      <div className="rounded-[22px] border border-sim/40 bg-sim/10 px-5 py-3">
        <p className="text-[17px] font-medium text-ink">{sim.data?.label ?? "Simulated / model-estimated"}</p>
        <p className="mt-0.5 text-sm text-ink-2">The edits are applied to the feature sequence and the model is re-run. Nothing is cut from your video.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section className="glass rounded-[28px] p-5" aria-label="Original vs simulated curve">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[19px] font-medium tracking-tight">Original vs simulated</h1>
            <MockBadge note={sim.data?._mock} />
          </div>
          {selected.length === 0 && <div className="mt-6"><EmptyState title="Select at least one edit to simulate." /></div>}
          {sim.isPending && selected.length > 0 && <div className="grid h-80 place-items-center"><Spinner label="Re-running the model on the edited sequence (a few seconds)" /></div>}
          {sim.isError && (isNotFound(sim.error) ? (
            <div className="mt-6"><EmptyState title="Simulation isn't available for this project yet." /></div>
          ) : <div className="mt-6 space-y-3">
              <ErrorBox error={sim.error} title="Couldn't simulate this selection" />
              <button
                type="button"
                className="pill-ghost"
                onClick={() => setParams({ edits: edits.filter((e) => e.simulatable !== false).map((e) => e.id).join(",") }, { replace: true })}
              >
                Use all suggested edits
              </button>
            </div>)}
          {sim.data && (
            <>
              <div className="mt-4 h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rows} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="t" type="number" domain={[0, sim.data.original_duration_s]} tickFormatter={mmss} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={46} />
                    <Tooltip content={<SimTooltip />} cursor={{ stroke: "rgba(255,255,255,0.25)" }} />
                    <Legend
                      verticalAlign="top"
                      align="left"
                      height={30}
                      formatter={(v: string) => (
                        <span className="text-xs text-ink-2">
                          {v === "original"
                            ? `Original (${mmss(sim.data!.original_duration_s)})`
                            : `Simulated after edits (${mmss(sim.data!.simulated_duration_s)}) · model-estimated`}
                        </span>
                      )}
                    />
                    <Line dataKey="original" stroke="var(--color-orig)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                    <Line dataKey="simulated" stroke="var(--color-sim)" strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-ink-3">
                Each curve uses its own running time: the simulated version is shorter because cut time is removed.
              </p>
            </>
          )}
        </section>

        <aside className="space-y-4">
          {sim.data && (
            <section className="glass rounded-[28px] p-5" aria-label="Estimated difference">
              <p className="eyebrow">Model-estimated difference</p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div className="rounded-2xl bg-white/[0.05] p-4">
                  <p className="text-[26px] font-medium tracking-tight tabular-nums">
                    {sim.data.delta.end_retention_pp >= 0 ? "+" : ""}
                    {sim.data.delta.end_retention_pp.toFixed(1)} pp
                  </p>
                  <p className="mt-1 text-xs text-ink-2">Retention at the end</p>
                </div>
                <div className="rounded-2xl bg-white/[0.05] p-4">
                  <p className="text-[26px] font-medium tracking-tight tabular-nums">
                    {sim.data.delta.avg_retention_pp >= 0 ? "+" : ""}
                    {sim.data.delta.avg_retention_pp.toFixed(1)} pp
                  </p>
                  <p className="mt-1 text-xs text-ink-2">Average retention</p>
                </div>
              </div>
              <p className="mt-3 text-xs text-ink-3">Percentage points, simulated. Not a promise of real viewer behaviour.</p>
            </section>
          )}

          <section className="glass rounded-[28px] p-5" aria-label="Edits to simulate">
            <p className="text-[15px] font-medium">Edits to simulate</p>
            {flagsQ.isPending && <div className="mt-3"><Spinner label="Loading edits" /></div>}
            {flagsQ.isError && <div className="mt-3"><ErrorBox error={flagsQ.error} title="Couldn't load the edits" /></div>}
            <ul className="mt-3 space-y-2">
              {edits.map((e) => (
                <li key={e.id}>
                  <label className="flex cursor-pointer gap-3 rounded-2xl bg-white/[0.04] p-3 hover:bg-white/[0.07]">
                    <input
                      type="checkbox"
                      checked={selected.includes(e.id)}
                      disabled={e.simulatable === false}
                      onChange={() => toggle(e.id)}
                      className="mt-0.5 size-4 accent-[var(--color-accent)] disabled:opacity-30"
                    />
                    <span className="text-[13px]">
                      <span className="font-medium text-ink">{editSentence(e.action, e.start, e.end, e.target_time)}</span>
                      <span className="block text-ink-2">{e.reason}</span>
                      <span className="mt-1 inline-block rounded bg-white/[0.06] px-1.5 text-[10px] font-semibold tracking-wide text-ink-3">
                        {ACTION_LABEL[e.action].toUpperCase()}
                        {e.simulatable === false && " · advice only, not simulated"}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            {!!sim.data?.skipped_edit_ids?.length && (
              <p className="mt-3 text-xs text-[#f6d391]">
                Not applied: {sim.data.skipped_edit_ids.join(", ")} (overlapping or advice-only edits).
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
