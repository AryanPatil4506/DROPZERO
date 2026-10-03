import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { useFlags, usePrediction, useProject, useScores, useValidation } from "../api/hooks";
import { Spinner } from "../components/ui";
import { CATEGORY_LABEL, LANGUAGE_LABEL, mmss, pct, range } from "../lib/format";

const SOURCE = { model: "Model", rule: "Evidence rule", "model+rule": "Model + rule" } as const;
const STATUS: Record<string, string> = { kept: "Kept", late: "Kept late", open: "Never paid off" };

function mean(xs: (number | null)[]): number | null {
  const v = xs.filter((x): x is number => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

/** One-click creator report: a light, printable page. "Download PDF" opens the browser's print
 * dialog (choose "Save as PDF"), which keeps Hindi/Devanagari text exact and works offline. */
export default function ReportPage() {
  const { id = "" } = useParams();
  const project = useProject(id);
  const pred = usePrediction(id);
  const flagsQ = useFlags(id);
  const scores = useScores(id);
  const validation = useValidation();

  if (project.isPending || pred.isPending || flagsQ.isPending) {
    return <div className="grid min-h-svh place-items-center"><Spinner label="Building the report" /></div>;
  }
  const p = project.data;
  const prediction = pred.data;
  const fl = flagsQ.data;
  if (!p || !prediction || !fl) {
    return <div className="p-10 text-ink">This project has no analysis yet. Run it first, then open the report.</div>;
  }
  const end = prediction.points[prediction.points.length - 1];
  const promise = fl.promise;
  const ledger = fl.ledger ?? [];
  const flags = [...fl.flags].sort((a, b) => (a.severity === b.severity ? a.start - b.start : a.severity === "high" ? -1 : 1));
  const edits = new Map(fl.edits.map((e) => [e.id, e]));
  const high = flags.filter((f) => f.severity === "high").length;
  const v = validation.data;
  const lanes = scores.data
    ? (["pacing", "content", "visual", "audio"] as const).map((k) => ({ k, v: mean(scores.data!.segments.map((s) => s[k])) }))
    : [];

  return (
    <div className="min-h-svh bg-[#f4f2ed] py-8 text-[#14171f] print:bg-white print:py-0">
      <div className="mx-auto max-w-[900px] space-y-6 bg-white p-10 shadow-sm print:max-w-none print:p-0 print:shadow-none">
        <div className="flex items-center justify-between gap-4 print:hidden">
          <Link to={`/projects/${id}`} className="text-sm text-[#5a6070] hover:text-[#14171f]">← Back to the dashboard</Link>
          <button type="button" onClick={() => window.print()} className="rounded-full bg-[#ff5a36] px-5 py-2 text-sm font-semibold text-[#14171f]">
            Download PDF
          </button>
        </div>

        <header className="border-b border-[#e3e0d8] pb-5">
          <p className="text-xs font-semibold tracking-[0.2em] text-[#d8431f] uppercase">DROPZERO creator report</p>
          <h1 className="mt-2 text-3xl font-semibold leading-tight">{p.title}</h1>
          <p className="mt-2 text-sm text-[#5a6070]">
            {LANGUAGE_LABEL[p.language] ?? p.language} · {CATEGORY_LABEL[p.category] ?? p.category} · {p.duration_s ? mmss(p.duration_s) : "–"} ·{" "}
            {p.source_type === "video" ? "video" : "script (timing estimated)"} · generated {new Date().toLocaleString()} · model {prediction.model_version}
          </p>
        </header>

        <section className="grid grid-cols-3 gap-4">
          <div className="rounded-2xl bg-[#f4f2ed] p-4">
            <p className="text-xs text-[#5a6070]">Model-estimated retention at the end</p>
            <p className="mt-1 text-3xl font-semibold">{pct(end.retention)}</p>
            <p className="text-xs text-[#5a6070]">likely range {pct(end.lower)}–{pct(end.upper)}</p>
          </div>
          <div className="rounded-2xl bg-[#f4f2ed] p-4">
            <p className="text-xs text-[#5a6070]">Issues found</p>
            <p className="mt-1 text-3xl font-semibold">{flags.length}</p>
            <p className="text-xs text-[#5a6070]">{high} high · {flags.length - high} medium</p>
          </div>
          <div className="rounded-2xl bg-[#f4f2ed] p-4">
            <p className="text-xs text-[#5a6070]">Title promise first addressed</p>
            <p className="mt-1 text-3xl font-semibold">{promise?.first_mention_s != null ? mmss(promise.first_mention_s) : "never"}</p>
            <p className="truncate text-xs text-[#5a6070]">“{promise?.title ?? p.title}”</p>
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Predicted retention</h2>
          <p className="text-xs text-[#5a6070]">{prediction.label}</p>
          <LineChart width={820} height={220} data={prediction.points} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="#e3e0d8" />
            <XAxis dataKey="t" type="number" domain={[0, end.t]} tickFormatter={mmss} tick={{ fill: "#5a6070", fontSize: 11 }} />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(x: number) => `${Math.round(x * 100)}%`} tick={{ fill: "#5a6070", fontSize: 11 }} width={44} />
            <Line dataKey="upper" stroke="#c9c4b8" dot={false} strokeDasharray="4 4" isAnimationActive={false} />
            <Line dataKey="lower" stroke="#c9c4b8" dot={false} strokeDasharray="4 4" isAnimationActive={false} />
            <Line dataKey="retention" stroke="#d8431f" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Issues and suggested edits</h2>
          <table className="mt-2 w-full border-collapse text-left text-sm">
            <thead className="text-xs text-[#5a6070]">
              <tr className="border-b border-[#e3e0d8]">
                <th className="py-2 pr-2 font-medium">Time</th>
                <th className="py-2 pr-2 font-medium">Severity</th>
                <th className="py-2 pr-2 font-medium">Issue</th>
                <th className="py-2 pr-2 font-medium">Suggested edit</th>
                <th className="py-2 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {flags.map((f) => (
                <tr key={f.id} className="break-inside-avoid border-b border-[#efece5] align-top">
                  <td className="py-2 pr-2 whitespace-nowrap tabular-nums">{range(f.start, f.end)}</td>
                  <td className="py-2 pr-2">{f.severity === "high" ? "High" : "Medium"}</td>
                  <td className="py-2 pr-2">{f.title}</td>
                  <td className="py-2 pr-2 text-[#3a3f4b]">{f.edit_ids.map((e) => edits.get(e)?.reason).filter(Boolean).join("; ") || "Review"}</td>
                  <td className="py-2 text-xs text-[#5a6070]">{f.source ? SOURCE[f.source] : ""}</td>
                </tr>
              ))}
              {flags.length === 0 && <tr><td colSpan={5} className="py-3 text-[#5a6070]">No issues flagged.</td></tr>}
            </tbody>
          </table>
        </section>

        {ledger.length > 0 && (
          <section className="break-inside-avoid">
            <h2 className="text-lg font-semibold">Promise ledger</h2>
            <table className="mt-2 w-full border-collapse text-left text-sm">
              <tbody>
                {ledger.map((pr, i) => (
                  <tr key={i} className="border-b border-[#efece5] align-top">
                    <td className="py-2 pr-2 whitespace-nowrap tabular-nums">{pr.source === "title" ? "Title" : mmss(pr.made_at)}</td>
                    <td className="py-2 pr-2">{pr.text}</td>
                    <td className="py-2 pr-2 whitespace-nowrap">{pr.payoff_at != null ? `paid off ${mmss(pr.payoff_at)}` : "—"}</td>
                    <td className="py-2 font-medium">{STATUS[pr.status] ?? pr.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {lanes.length > 0 && (
          <section className="break-inside-avoid">
            <h2 className="text-lg font-semibold">Score lanes (average over the video)</h2>
            <div className="mt-2 grid grid-cols-4 gap-3">
              {lanes.map((l) => (
                <div key={l.k} className="rounded-xl bg-[#f4f2ed] p-3">
                  <p className="text-xs text-[#5a6070] capitalize">{l.k === "audio" ? "audio clarity" : l.k}</p>
                  <p className="text-2xl font-semibold">{l.v == null ? "n/a" : Math.round(l.v)}</p>
                </div>
              ))}
            </div>
            <p className="mt-1 text-xs text-[#5a6070]">DROPZERO internal scores (0–100), relative to this video; not validated against retention data.</p>
          </section>
        )}

        {v && (
          <section className="break-inside-avoid rounded-2xl border border-[#e3e0d8] p-4 text-sm">
            <h2 className="text-lg font-semibold">How reliable is this?</h2>
            <p className="mt-1 text-[#3a3f4b]">
              On {v.n_videos_test} held-out lectures the model's curve error was {v.metrics.mae.toFixed(3)} vs {v.baseline.mae.toFixed(3)} for an average-curve baseline, and its drop flags were right {pct(v.detection.precision)} of the time vs {pct((v as unknown as { baseline_detection: { precision: number } }).baseline_detection.precision)}. It caught {v.detection.detected.toLocaleString()} of {v.detection.total.toLocaleString()} major drops (the baseline caught more). Data: {v.dataset}.
            </p>
          </section>
        )}

        <footer className="border-t border-[#e3e0d8] pt-4 text-xs text-[#5a6070]">
          Curves and simulations are model estimates, not guaranteed outcomes. Evidence-rule flags are measured directly but are not validated against retention data. Scores are DROPZERO internal scores, not YouTube analytics. Your original video is never modified.
        </footer>
      </div>
    </div>
  );
}
