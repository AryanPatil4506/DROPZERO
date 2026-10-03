import { useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Area, ComposedChart, Line, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { usePrediction, useProject, useRender, useSimulation } from "../api/hooks";
import type { CurvePoint, CustomEdit } from "../api/types";
import { IconChevron, IconPause, IconPlay, IconRestart } from "../components/icons";
import { ErrorBox, Spinner } from "../components/ui";
import { mmss } from "../lib/format";

function MiniCurve({ points, duration, time, color }: { points: CurvePoint[]; duration: number; time: number; color: string }) {
  const rows = points.map((p) => ({ t: p.t, retention: p.retention, band: [p.lower, p.upper] as [number, number] }));
  return (
    <div className="h-28">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
          <XAxis dataKey="t" type="number" domain={[0, duration]} tickFormatter={mmss} tick={{ fill: "var(--color-ink-3)", fontSize: 10 }} axisLine={false} tickLine={false} height={18} />
          <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} tick={{ fill: "var(--color-ink-3)", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
          <Area dataKey="band" stroke="none" fill={color} fillOpacity={0.14} isAnimationActive={false} />
          <Line dataKey="retention" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
          <ReferenceLine x={time} stroke="var(--color-accent)" strokeWidth={1.5} ifOverflow="hidden" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Before/after: the original and the rendered edit play side by side (shared play/pause/restart),
 * each with its predicted curve. The edited curve is the model simulation of the same plan.
 */
export default function ComparePage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const renderId = params.get("render");
  const editIds = useMemo(() => (params.get("edits") ?? "").split(",").filter(Boolean), [params]);
  const custom = useMemo<CustomEdit[]>(() => {
    try {
      return JSON.parse(params.get("custom") ?? "[]") as CustomEdit[];
    } catch {
      return [];
    }
  }, [params]);

  const project = useProject(id);
  const prediction = usePrediction(id);
  const render = useRender(id, renderId);
  const sim = useSimulation(id, editIds, custom);

  const origRef = useRef<HTMLVideoElement>(null);
  const editRef = useRef<HTMLVideoElement>(null);
  const [tOrig, setTOrig] = useState(0);
  const [tEdit, setTEdit] = useState(0);
  const [playing, setPlaying] = useState(false);

  const both = () => [origRef.current, editRef.current].filter((v): v is HTMLVideoElement => !!v);
  const play = () => {
    for (const v of both()) void v.play().catch(() => undefined);
    setPlaying(true);
  };
  const pause = () => {
    for (const v of both()) v.pause();
    setPlaying(false);
  };
  const restart = () => {
    for (const v of both()) v.currentTime = 0;
    play();
  };

  const st = render.data;
  const plan = st?.plan ?? null;
  const origDur = project.data?.duration_s ?? plan?.source_duration_s ?? 0;
  const editDur = plan?.output_duration_s ?? sim.data?.simulated_duration_s ?? 0;
  const removed = origDur && editDur ? origDur - editDur : null;

  return (
    <div className="mx-auto max-w-[1500px] space-y-4 p-5">
      <nav className="flex items-center gap-2 text-sm text-ink-3">
        <Link to="/projects" className="hover:text-ink">Projects</Link>
        <IconChevron className="size-3.5" />
        <Link to={`/projects/${id}`} className="hover:text-ink">{project.data?.title ?? "Project"}</Link>
        <IconChevron className="size-3.5" />
        <span className="text-ink">Before / after</span>
      </nav>

      <div className="rounded-[22px] border border-sim/40 bg-sim/10 px-5 py-3">
        <p className="text-[16px] font-medium">Rendered from your edit plan. Your original file is unchanged.</p>
        <p className="mt-0.5 text-sm text-ink-2">
          The edited copy is stored encrypted and deleted on the same schedule as uploads. Curves are model estimates, not measured retention.
        </p>
      </div>

      {!renderId && <ErrorBox error="No render selected. Start one from the dashboard's Edit plan." title="Nothing to compare" />}
      {render.isError && <ErrorBox error={render.error} title="Couldn't load the render" />}
      {st && (st.status === "queued" || st.status === "running") && (
        <div className="glass grid h-64 place-items-center rounded-[28px]">
          <Spinner label={st.status === "queued" ? "Waiting for the renderer" : "Rendering the edited version with FFmpeg"} />
        </div>
      )}
      {st?.status === "failed" && <ErrorBox error={st.error ?? "Render failed"} title="Render failed" />}

      {st?.status === "done" && (
        <>
          <div className="glass flex flex-wrap items-center gap-3 rounded-full p-1.5 pr-5">
            <button type="button" aria-label="Restart both" onClick={restart} className="grid size-11 place-items-center rounded-full bg-white/[0.07] text-ink-2 hover:text-ink">
              <IconRestart className="size-5" />
            </button>
            <button
              type="button"
              aria-label={playing ? "Pause both" : "Play both"}
              onClick={playing ? pause : play}
              className="grid size-12 place-items-center rounded-full bg-ink text-[#0a0a0b]"
            >
              {playing ? <IconPause className="size-5" /> : <IconPlay className="size-5 translate-x-px" />}
            </button>
            <span className="text-sm text-ink-2">Plays both from the same moment. Each keeps its own timeline.</span>
            <span className="ml-auto text-sm text-ink-2 tabular-nums">
              {removed != null && removed > 0.5 ? `${mmss(origDur)} → ${mmss(editDur)} (−${Math.round(removed)} s)` : `${mmss(editDur)}`}
            </span>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="glass rounded-[28px] p-4" aria-label="Original">
              <div className="flex items-baseline justify-between px-1">
                <h2 className="text-[16px] font-medium">Original</h2>
                <span className="text-xs text-ink-3 tabular-nums">{mmss(tOrig)} / {mmss(origDur)}</span>
              </div>
              <video
                ref={origRef}
                src={api.mediaUrl(id)}
                className="mt-3 aspect-video w-full rounded-2xl bg-black"
                controls
                preload="metadata"
                onTimeUpdate={(e) => setTOrig(e.currentTarget.currentTime)}
              />
              <p className="mt-3 px-1 text-xs text-ink-2">Predicted retention (original)</p>
              {prediction.data ? (
                <MiniCurve points={prediction.data.points} duration={origDur} time={tOrig} color="var(--color-orig)" />
              ) : prediction.isError ? (
                <p className="px-1 py-3 text-xs text-ink-3">No prediction for this project yet ({(prediction.error as Error).message}).</p>
              ) : (
                <Spinner label="Loading prediction" />
              )}
            </section>

            <section className="glass rounded-[28px] p-4" aria-label="Edited">
              <div className="flex items-baseline justify-between px-1">
                <h2 className="text-[16px] font-medium">Edited</h2>
                <span className="text-xs text-ink-3 tabular-nums">{mmss(tEdit)} / {mmss(editDur)}</span>
              </div>
              <video
                ref={editRef}
                src={api.renderUrl(id, st.render_id)}
                className="mt-3 aspect-video w-full rounded-2xl bg-black"
                controls
                preload="metadata"
                onTimeUpdate={(e) => setTEdit(e.currentTarget.currentTime)}
              />
              <p className="mt-3 px-1 text-xs text-ink-2">Simulated retention (edited) · model-estimated</p>
              {sim.data ? (
                <MiniCurve points={sim.data.simulated} duration={editDur} time={tEdit} color="var(--color-sim)" />
              ) : sim.isError ? (
                <p className="px-1 py-3 text-xs text-ink-3">No simulated curve for this plan ({(sim.error as Error).message}).</p>
              ) : editIds.length || custom.length ? (
                <Spinner label="Simulating" />
              ) : (
                <p className="px-1 py-3 text-xs text-ink-3">This plan has no simulatable edits (moves are rendered but not simulated).</p>
              )}
            </section>
          </div>

          {plan && (
            <section className="glass rounded-[24px] px-5 py-4 text-sm text-ink-2">
              <p>
                <span className="text-ink">{plan.pieces.length}</span> pieces · applied {plan.applied_edit_ids.length} suggested edit
                {plan.applied_edit_ids.length === 1 ? "" : "s"}
                {plan.moved_edit_ids.length > 0 && `, moved ${plan.moved_edit_ids.length}`}
                {plan.applied_custom.length > 0 && `, ${plan.applied_custom.length} of your own`}
                {plan.skipped_edit_ids.length > 0 && ` · not rendered: ${plan.skipped_edit_ids.join(", ")} (advice-only or overlapping)`}
              </p>
              {(st.encoder || st.seconds != null) && (
                <p className="mt-1 text-xs text-ink-3">
                  Encoded with {st.encoder ?? "ffmpeg"}
                  {st.seconds != null && ` in ${st.seconds} s`}
                  {plan.moved_edit_ids.length > 0 && " · moves change the order of footage; the model doesn't simulate reordering"}
                </p>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
