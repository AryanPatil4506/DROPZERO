import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { useProjects } from "../api/hooks";
import type { ABMetric, ABResult } from "../api/types";
import { ErrorBox, Segmented, Spinner } from "../components/ui";
import { mmss, pct } from "../lib/format";

const LANGS = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "hinglish", label: "Hinglish" },
];

function fmt(m: ABMetric, v: number | string | null): string {
  if (v == null) return m.key === "title_at" ? "never" : "n/a";
  if (typeof v === "string") return v === "none" ? "no promise" : v;
  if (m.key === "r30" || m.key === "r60") return pct(v);
  if (m.key === "title_at") return mmss(v);
  if (m.key === "pace") return `${Math.round(v * 100)}% of average`;
  if (m.key === "dead_air") return `${v} s`;
  return String(v);
}

function Winner({ m, nameA, nameB }: { m: ABMetric; nameA: string; nameB: string }) {
  if (m.winner === "tie") return <span className="chip h-6 text-[11px]">No clear difference</span>;
  if (m.winner === "n/a") return <span className="text-xs text-ink-3">n/a</span>;
  return <span className="chip h-6 border-accent/60 text-[11px] text-accent">{m.winner === "a" ? nameA : nameB}</span>;
}

/** Hook A/B simulator: two script versions, compared before recording. A simulation, never a
 * real A/B test with viewers. */
export default function AbTestPage() {
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("en");
  const [nameA, setNameA] = useState("Version A");
  const [nameB, setNameB] = useState("Version B");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [state, setState] = useState<{ loading: boolean; data?: ABResult; error?: unknown }>({ loading: false });
  const [mode, setMode] = useState<"scripts" | "projects">("scripts");
  const [pa, setPa] = useState("");
  const [pb, setPb] = useState("");
  const projects = (useProjects().data ?? []).filter((p) => p.status === "ready");
  const runProjects = () => {
    setState({ loading: true });
    api
      .abCompareProjects(pa, pb)
      .then((data) => setState({ loading: false, data }))
      .catch((error) => setState({ loading: false, error }));
  };

  const ready = title.trim() && a.trim().length >= 20 && b.trim().length >= 20;
  const run = () => {
    setState({ loading: true });
    api
      .abTest({ title, language, script_a: a, script_b: b, name_a: nameA || "Version A", name_b: nameB || "Version B" })
      .then((data) => setState({ loading: false, data }))
      .catch((error) => setState({ loading: false, error }));
  };

  const rows = useMemo(() => {
    const d = state.data;
    if (!d) return [];
    const m = new Map<number, { t: number; a?: number; b?: number }>();
    for (const p of d.a.points) m.set(p.t, { ...m.get(p.t), t: p.t, a: p.retention });
    for (const p of d.b.points) m.set(p.t, { ...m.get(p.t), t: p.t, b: p.retention });
    return [...m.values()].sort((x, y) => x.t - y.t);
  }, [state.data]);

  const d = state.data;
  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-5">
      <div className="rounded-[22px] border border-sim/40 bg-sim/10 px-5 py-3">
        <p className="text-[17px] font-medium text-ink">Hook A/B simulator</p>
        <p className="mt-0.5 text-sm text-ink-2">
          Paste two versions of your script (for example two different openings). DROPZERO compares the hook signals it measures and the model-estimated curves. It is a simulation, not a real A/B test with viewers, and timing is estimated from word counts.
        </p>
      </div>

      <Segmented
        label="What to compare"
        value={mode}
        onChange={(v) => {
          setMode(v);
          setState({ loading: false });
        }}
        options={[
          { value: "scripts", label: "Paste two scripts" },
          { value: "projects", label: "Compare two uploads (video or script)" },
        ]}
      />

      {mode === "projects" && (
        <section className="glass space-y-4 rounded-[28px] p-5" aria-label="Uploads to compare">
          <p className="text-sm text-ink-2">
            Upload each version of your video as its own project (New analysis), then pick both here. Videos add two signals scripts can't: seconds without speech and scene cuts in the hook.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {[
              { v: pa, set: setPa, label: "Version A" },
              { v: pb, set: setPb, label: "Version B" },
            ].map((x) => (
              <label key={x.label} className="flex flex-col gap-1 text-sm text-ink-2">
                {x.label}
                <select value={x.v} onChange={(e) => x.set(e.target.value)} className="rounded-xl border border-line-2 bg-white/5 px-3 py-2 text-ink">
                  <option value="">Choose a project…</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} · {p.source_type === "video" ? "video" : "script"}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <button type="button" className="pill-accent h-10 px-5" disabled={!pa || !pb || pa === pb || state.loading} onClick={runProjects}>
            {state.loading ? "Comparing…" : "Compare uploads"}
          </button>
        </section>
      )}

      {mode === "scripts" && (
      <section className="glass space-y-4 rounded-[28px] p-5" aria-label="Versions to compare">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_200px]">
          <label className="flex flex-col gap-1 text-sm text-ink-2">
            Video title (the promise viewers clicked for)
            <input value={title} onChange={(e) => setTitle(e.target.value)} className="rounded-xl border border-line-2 bg-white/5 px-3 py-2 text-ink" placeholder="I Built an AI Agent in 24 Hours" />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink-2">
            Language
            <select value={language} onChange={(e) => setLanguage(e.target.value)} className="rounded-xl border border-line-2 bg-white/5 px-3 py-2 text-ink">
              {LANGS.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {[
            { name: nameA, setName: setNameA, text: a, setText: setA },
            { name: nameB, setName: setNameB, text: b, setText: setB },
          ].map((v, i) => (
            <div key={i} className="flex flex-col gap-2">
              <input value={v.name} onChange={(e) => v.setName(e.target.value)} aria-label={`Name of version ${i ? "B" : "A"}`} className="rounded-xl border border-line-2 bg-white/5 px-3 py-2 text-sm font-medium text-ink" />
              <textarea value={v.text} onChange={(e) => v.setText(e.target.value)} aria-label={`Script of version ${i ? "B" : "A"}`} rows={10} className="scroll-thin rounded-2xl border border-line-2 bg-white/5 p-3 text-sm leading-relaxed text-ink" placeholder="Paste the full script (TXT or Markdown)" />
            </div>
          ))}
        </div>
        <button type="button" className="pill-accent h-10 px-5" disabled={!ready || state.loading} onClick={run}>
          {state.loading ? "Comparing…" : "Compare versions"}
        </button>
      </section>
      )}

      {state.loading && <div className="grid h-40 place-items-center"><Spinner label="Analysing both versions (a few seconds)" /></div>}
      {state.error != null && <ErrorBox error={state.error} title="Couldn't compare these versions" />}

      {d && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section className="glass rounded-[28px] p-5" aria-label="Hook signals">
            <h2 className="text-[19px] font-medium tracking-tight">{d.summary}</h2>
            <table className="mt-4 w-full text-left text-sm">
              <thead className="text-ink-3">
                <tr>
                  <th className="pb-2 font-medium">Signal</th>
                  <th className="pb-2 font-medium">{d.a.name}</th>
                  <th className="pb-2 font-medium">{d.b.name}</th>
                  <th className="pb-2 font-medium">Better</th>
                </tr>
              </thead>
              <tbody>
                {d.metrics.map((m) => (
                  <tr key={m.key} className="border-t border-line-2" title={m.note ?? undefined}>
                    <td className="py-2 pr-2 text-ink-2">{m.label}</td>
                    <td className="py-2 pr-2 tabular-nums text-ink">{fmt(m, m.a)}</td>
                    <td className="py-2 pr-2 tabular-nums text-ink">{fmt(m, m.b)}</td>
                    <td className="py-2"><Winner m={m} nameA={d.a.name} nameB={d.b.name} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[d.a, d.b].map((v) => (
                <div key={v.name} className="rounded-2xl bg-white/[0.04] p-3 text-sm">
                  <p className="font-medium text-ink">{v.name} · flags in the first minute</p>
                  <ul className="mt-1 list-disc pl-5 text-ink-2">
                    {v.hook_flags.length ? v.hook_flags.map((f) => <li key={f}>{f}</li>) : <li>None</li>}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          <section className="glass rounded-[28px] p-5" aria-label="Model-estimated curves">
            <h2 className="text-[19px] font-medium tracking-tight">Model-estimated retention</h2>
            <p className="mt-1 text-xs text-ink-3">{d.label}</p>
            <div className="mt-4 h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="t" type="number" domain={[0, Math.max(d.a.duration_s, d.b.duration_s)]} tickFormatter={mmss} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={46} />
                  <Tooltip formatter={(v) => (typeof v === "number" ? pct(v) : String(v))} labelFormatter={(t) => (typeof t === "number" ? mmss(t) : String(t))} contentStyle={{ background: "rgba(18,21,28,0.92)", border: "none", borderRadius: 12 }} />
                  <Legend verticalAlign="top" align="left" height={30} formatter={(k: string) => <span className="text-xs text-ink-2">{k === "a" ? d.a.name : d.b.name}</span>} />
                  <Line dataKey="a" type="monotone" stroke="var(--color-orig)" strokeWidth={2} dot={false} connectNulls />
                  <Line dataKey="b" type="monotone" stroke="var(--color-sim)" strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
