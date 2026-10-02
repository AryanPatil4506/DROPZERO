import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { isNotFound } from "../api/errors";
import { useFlags, usePrediction, useProject, useProjects, useScores, useSegments, useTextFeatures, useTranscript } from "../api/hooks";
import type { Flag } from "../api/types";
import AnalysisPanel from "../components/dashboard/AnalysisPanel";
import BackgroundStage from "../components/dashboard/BackgroundStage";
import EditPlan from "../components/dashboard/EditPlan";
import PromiseLedger from "../components/dashboard/PromiseLedger";
import FlagsList from "../components/dashboard/FlagsList";
import PlaybackCapsule from "../components/dashboard/PlaybackCapsule";
import RetentionChart from "../components/dashboard/RetentionChart";
import RiskDrawer from "../components/dashboard/RiskDrawer";
import {
  skipTarget,
  TimelineContext,
  type CustomCut,
  type TimeRange,
  type TimelineState,
} from "../components/dashboard/timeline-context";
import Tracks from "../components/dashboard/Tracks";
import TranscriptPanel from "../components/dashboard/TranscriptPanel";
import { IconChevron, IconClose, IconMinus, IconPlus, IconVideo } from "../components/icons";
import { EmptyState, ErrorBox, EstimatedBadge, MockBadge, Segmented, Spinner } from "../components/ui";
import { mmss } from "../lib/format";

const ZOOMS = [1, 2, 4];
const SKIPPABLE = new Set(["CUT", "SHORTEN"]);


export default function Dashboard() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const project = useProject(id);
  const projects = useProjects();
  const transcript = useTranscript(id);
  const segments = useSegments(id);
  const features = useTextFeatures(id);
  const prediction = usePrediction(id);
  const flagsQ = useFlags(id);

  const [time, setTime] = useState(0);
  const [playing, setPlayingState] = useState(false);
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null);
  const [cut, setCut] = useState<TimeRange | null>(null);
  const [zoom, setZoom] = useState(1);
  const [acceptedEditIds, setAcceptedEditIds] = useState<string[]>([]);
  const [customCuts, setCustomCuts] = useState<CustomCut[]>([]);
  const [previewEdited, setPreviewEditedState] = useState(false);
  const [shelfTab, setShelfTab] = useState<"timeline" | "edits" | "promises">("timeline");
  const [laneMode, setLaneMode] = useState<"structure" | "scores">("structure");
  const [localVideo, setLocalVideo] = useState<string | null>(null);
  // Dev only: ?demoVideo=/demo/clip.mp4 plays a sample file from public/ (never in production builds).
  const [demoVideo] = useState(() => (import.meta.env.DEV ? new URLSearchParams(location.search).get("demoVideo") : null));
  const [mediaFailed, setMediaFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const clockRef = useRef(0); // playhead when there is no media, mirrored into `time`

  const isVideo = project.data?.source_type === "video";
  const src = localVideo ?? demoVideo ?? (isVideo && !mediaFailed ? api.mediaUrl(id) : null);
  const hasMedia = !!src;
  const duration =
    project.data?.duration_s ?? transcript.data?.duration_s ?? segments.data?.[segments.data.length - 1]?.end ?? 0;
  const flags = useMemo(() => flagsQ.data?.flags ?? [], [flagsQ.data]);
  const edits = useMemo(() => flagsQ.data?.edits ?? [], [flagsQ.data]);
  const selectedFlag = flags.find((f) => f.id === selectedFlagId) ?? null;
  const brokenPromises = (flagsQ.data?.ledger ?? []).filter((x) => x.status !== "kept").length;
  const scoresQ = useScores(id);
  const hasScores = !!scoresQ.data;

  // Ranges skipped when previewing the edit plan: accepted CUT/SHORTEN edits plus custom cuts.
  const skipRanges = useMemo(() => {
    const ranges = [
      ...edits.filter((e) => acceptedEditIds.includes(e.id) && SKIPPABLE.has(e.action)).map((e) => ({ start: e.start, end: e.end })),
      ...customCuts.filter((c) => c.action !== "SPEED").map((c) => ({ start: c.start, end: c.end })),
    ].sort((a, b) => a.start - b.start);
    const merged: TimeRange[] = [];
    for (const r of ranges) {
      const last = merged[merged.length - 1];
      if (last && r.start <= last.end) last.end = Math.max(last.end, r.end);
      else merged.push({ ...r });
    }
    return merged;
  }, [edits, acceptedEditIds, customCuts]);
  const previewing = previewEdited && skipRanges.length > 0;

  useEffect(() => () => {
    if (localVideo) URL.revokeObjectURL(localVideo);
  }, [localVideo]);

  const seek = useCallback(
    (t: number) => {
      const clamped = Math.min(Math.max(0, t), duration || t);
      clockRef.current = clamped;
      setTime(clamped);
      if (videoRef.current) videoRef.current.currentTime = clamped;
    },
    [duration],
  );

  const setPlaying = useCallback(
    (p: boolean) => {
      const v = videoRef.current;
      if (hasMedia && v) {
        if (p) void v.play().catch(() => setPlayingState(false));
        else v.pause();
        return;
      }
      if (p && clockRef.current >= duration) {
        clockRef.current = 0;
        setTime(0);
      }
      setPlayingState(p);
    },
    [hasMedia, duration],
  );

  const restart = useCallback(() => {
    seek(0);
    setPlaying(true);
  }, [seek, setPlaying]);

  // Media time updates; in edited preview, jump over accepted cuts.
  const onMediaTime = useCallback(
    (t: number) => {
      const target = previewing ? skipTarget(t, skipRanges) : null;
      if (target != null && videoRef.current) {
        videoRef.current.currentTime = target;
        setTime(target);
        return;
      }
      setTime(t);
    },
    [previewing, skipRanges],
  );

  // No media (script mode): a virtual clock moves the playhead through the estimated timing.
  useEffect(() => {
    if (!playing || hasMedia) return;
    let last = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      let next = Math.min(duration, clockRef.current + (now - last) / 1000);
      last = now;
      const target = previewing ? skipTarget(next, skipRanges) : null;
      if (target != null) next = target;
      clockRef.current = next;
      setTime(next);
      if (next >= duration) {
        clearInterval(timer);
        setPlayingState(false);
      }
    }, 40);
    return () => clearInterval(timer);
  }, [playing, hasMedia, duration, previewing, skipRanges]);

  const view = useMemo<TimeRange>(() => {
    if (zoom === 1 || !duration) return { start: 0, end: duration || 1 };
    const span = duration / zoom;
    const start = Math.min(Math.max(0, time - span / 2), duration - span);
    return { start, end: start + span };
  }, [zoom, duration, time]);

  const pickFlag = useCallback((flag: Flag | null) => setSelectedFlagId(flag?.id ?? null), []);

  const ctx: TimelineState = {
    duration,
    time,
    seek,
    playing,
    setPlaying,
    restart,
    selectedFlagId,
    selectFlag: setSelectedFlagId,
    cut,
    setCut,
    view,
    zoom,
    setZoom,
    acceptedEditIds,
    toggleEdit: (editId) =>
      setAcceptedEditIds((ids) => (ids.includes(editId) ? ids.filter((x) => x !== editId) : [...ids, editId])),
    setAcceptedEditIds,
    customCuts,
    addCustomCut: (r) =>
      setCustomCuts((cs) => [
        ...cs,
        { id: `my-${Date.now()}`, action: r.action ?? "CUT", factor: r.factor, start: Math.min(r.start, r.end), end: Math.max(r.start, r.end) },
      ]),
    removeCustomCut: (cutId) => setCustomCuts((cs) => cs.filter((c) => c.id !== cutId)),
    previewEdited: previewing,
    setPreviewEdited: setPreviewEditedState,
    skipRanges,
  };

  if (project.isPending) return <div className="p-8"><Spinner label="Loading project" /></div>;
  if (project.isError) return <div className="p-8"><ErrorBox error={project.error} title="Couldn't load this project" /></div>;
  const p = project.data;
  const estimated = transcript.data?.timing_source === "estimated";
  const predictionMissing = prediction.isError && isNotFound(prediction.error);

  const list = projects.data ?? [];
  const pos = list.findIndex((x) => x.id === id);
  const go = (delta: number) => {
    if (list.length < 2 || pos < 0) return;
    navigate(`/projects/${list[(pos + delta + list.length) % list.length].id}`);
  };

  return (
    <TimelineContext.Provider value={ctx}>
      <div className="relative h-full min-h-[680px] overflow-hidden">
        {/* the video (or, in script mode, a teleprompter) runs behind everything */}
        <BackgroundStage
          src={src}
          videoRef={videoRef}
          transcript={transcript.data ?? null}
          onTime={onMediaTime}
          onPlayState={setPlayingState}
          onError={() => {
            if (localVideo) return;
            setMediaFailed(true);
            setPlayingState(false);
          }}
        />

        {/* analytics float in front */}
        <div className="pointer-events-none relative grid h-full grid-cols-[minmax(270px,310px)_minmax(0,1fr)_minmax(300px,350px)] grid-rows-[auto_minmax(0,1fr)_auto] gap-3 p-3 [&>*]:pointer-events-auto">
          {/* header */}
          <header className="col-span-2 flex min-w-0 items-center gap-x-2.5 px-1">
            <Link to="/projects" className="text-sm text-ink-3 hover:text-ink">Projects</Link>
            <IconChevron className="size-3.5 shrink-0 text-ink-3" />
            <h1 className="min-w-[120px] truncate text-[19px] font-medium tracking-tight [text-shadow:0_2px_16px_rgba(0,0,0,0.6)]">{p.title}</h1>
            {estimated && <EstimatedBadge />}
            <MockBadge note={prediction.data?._mock} />
            {p.warnings.length > 0 && (
              <span className="chip shrink-0 border-med/40 bg-black/30 text-[#f6d391]" title={p.warnings.join("\n")}>
                ⚠ {p.warnings.length} warning{p.warnings.length > 1 ? "s" : ""}
              </span>
            )}
            <div className="ml-auto flex shrink-0 items-center gap-1">
              <label
                className="chip h-8 cursor-pointer bg-black/30 px-3 hover:text-ink"
                title={isVideo ? "Play your local copy of this video (it stays in your browser)" : "Script projects have no video. A recording you attach is for preview only; script timing is estimated, so it may not line up."}
              >
                <IconVideo className="size-4" />
                {localVideo ? "Change video" : isVideo ? "Load local copy" : "Attach recording"}
                <input
                  type="file"
                  accept="video/mp4,video/quicktime,.mp4,.mov"
                  className="sr-only"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    setLocalVideo(URL.createObjectURL(f));
                    setPlayingState(false);
                    seek(0);
                  }}
                />
              </label>
              {list.length > 1 && (
                <div className="glass ml-1 flex items-center rounded-full p-1 text-[13px]">
                  <button type="button" aria-label="Previous project" onClick={() => go(-1)} className="grid size-7 place-items-center rounded-full text-ink-2 hover:text-ink">
                    <IconChevron className="size-3.5 rotate-180" />
                  </button>
                  <span className="px-1.5 text-ink-2 tabular-nums">{pos + 1}/{list.length}</span>
                  <button type="button" aria-label="Next project" onClick={() => go(1)} className="grid size-7 place-items-center rounded-full text-ink-2 hover:text-ink">
                    <IconChevron className="size-3.5" />
                  </button>
                  <Link to="/projects" aria-label="Close project" className="grid size-7 place-items-center rounded-full text-ink-2 hover:text-ink">
                    <IconClose className="size-3.5" />
                  </Link>
                </div>
              )}
            </div>
          </header>

          {/* left: analysis + transcript */}
          <div className="flex min-h-0 flex-col gap-3">
            <AnalysisPanel project={p} flags={flags} segments={segments.data ?? []} features={features.data ?? null} promise={flagsQ.data?.promise} />
            <div className="min-h-0 flex-1">
              {transcript.isPending && <div className="glass rounded-[26px] p-4"><Spinner label="Loading transcript" /></div>}
              {transcript.isError && <ErrorBox error={transcript.error} title="Couldn't load the transcript" />}
              {transcript.data && (
                <div className="h-full">
                  <TranscriptPanel transcript={transcript.data} features={features.data ?? null} flags={flags} large={!isVideo} />
                </div>
              )}
            </div>
          </div>

          {/* centre: the video shows through; transport floats over it */}
          <div className="pointer-events-none flex min-h-0 flex-col items-end justify-end gap-2 [&>*]:pointer-events-auto">
            {isVideo && mediaFailed && !localVideo && (
              <p className="glass max-w-sm rounded-2xl px-4 py-2.5 text-[13px] text-ink-2">
                Video streaming isn't available from the API yet. Use <span className="text-ink">Load local copy</span> to play your file here.
              </p>
            )}
            {previewing && (
              <span className="chip border-accent/50 bg-black/50 text-accent">Edited preview · skipping {skipRanges.length} cut{skipRanges.length > 1 ? "s" : ""}</span>
            )}
            <PlaybackCapsule />
          </div>

          {/* right: flags + "Why would I leave?" */}
          <aside className="scroll-thin row-span-3 row-start-1 col-start-3 min-h-0 space-y-3 overflow-y-auto">
            {flagsQ.isPending && <div className="glass rounded-[26px] p-4"><Spinner label="Loading flags" /></div>}
            {flagsQ.isError && !isNotFound(flagsQ.error) && <ErrorBox error={flagsQ.error} title="Couldn't load flags" />}
            {flags.length > 0 && <FlagsList flags={flags} />}
            {!flagsQ.isPending && (
              <RiskDrawer
                projectId={id}
                flag={selectedFlag}
                edits={edits}
                flagCount={flags.length}
                unavailable={flagsQ.isError && isNotFound(flagsQ.error)}
              />
            )}
          </aside>

          {/* bottom shelf: timeline | edit plan */}
          <section className="glass col-span-2 rounded-[28px] px-3.5 pt-2 pb-2.5" aria-label="Timeline and edit plan">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-1">
              <Segmented
                label="Shelf view"
                value={shelfTab}
                onChange={setShelfTab}
                options={[
                  { value: "timeline", label: "Timeline" },
                  { value: "edits", label: `Edit plan${acceptedEditIds.length + customCuts.length ? ` (${acceptedEditIds.length + customCuts.length})` : ""}` },
                  { value: "promises", label: `Promises${brokenPromises ? ` (${brokenPromises})` : ""}` },
                ]}
              />
              {shelfTab === "timeline" ? (
                <>
                  <div className="flex items-center gap-3 text-xs text-ink-2">
                    <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 rounded bg-pred" />Predicted</span>
                    <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-4 rounded-sm bg-pred/25" />Range</span>
                    <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-high" />High</span>
                    <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-med" />Medium</span>
                    {scoresQ.data && laneMode === "scores" && (
                      <span className="inline-flex items-center gap-1.5 border-l border-line pl-3" title={scoresQ.data.label}>
                        Scores
                        <i className="h-2 w-3 rounded-sm bg-ok/70" />good
                        <i className="h-2 w-3 rounded-sm bg-med/70" />fair
                        <i className="h-2 w-3 rounded-sm bg-high/70" />weak
                        <span className="text-ink-3">(internal)</span>
                      </span>
                    )}
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    {hasScores && (
                      <Segmented
                        label="Lanes"
                        value={laneMode}
                        onChange={setLaneMode}
                        options={[
                          { value: "structure", label: "Structure" },
                          { value: "scores", label: "Scores" },
                        ]}
                      />
                    )}
                    <span className="text-xs text-ink-3 tabular-nums">{zoom}×</span>
                    <div className="flex rounded-full bg-white/[0.06] p-1">
                      <button type="button" aria-label="Zoom out" disabled={zoom === ZOOMS[0]} onClick={() => setZoom(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)])} className="grid size-8 place-items-center rounded-full text-ink-2 hover:text-ink disabled:opacity-30">
                        <IconMinus className="size-4" />
                      </button>
                      <button type="button" aria-label="Zoom in" disabled={zoom === ZOOMS[ZOOMS.length - 1]} onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)])} className="grid size-8 place-items-center rounded-full text-ink-2 hover:text-ink disabled:opacity-30">
                        <IconPlus className="size-4" />
                      </button>
                    </div>
                  </div>
                </>
              ) : shelfTab === "edits" ? (
                <p className="text-xs text-ink-3">Accept suggestions or mark your own cuts. This is an edit plan; your original file is never changed.</p>
              ) : (
                <p className="text-xs text-ink-3">Promises made in the title and opening, and when they pay off. Late or never-kept promises are flagged.</p>
              )}
            </div>

            <div className="mt-1.5 h-[208px]">
              {shelfTab === "timeline" ? (
                <div className="flex h-full flex-col">
                  {prediction.isPending && <div className="grid h-[100px] place-items-center"><Spinner label="Loading prediction" /></div>}
                  {predictionMissing && (
                    <div className="grid h-[100px] place-items-center px-6">
                      <EmptyState title="No retention prediction for this project yet">
                        The model step isn't available for this project. Segments, topics and the transcript are still live.
                      </EmptyState>
                    </div>
                  )}
                  {prediction.isError && !predictionMissing && <ErrorBox error={prediction.error} title="Couldn't load the prediction" />}
                  {prediction.data && <RetentionChart prediction={prediction.data} flags={flags} onPickFlag={pickFlag} height={100} />}
                  <div className="mt-1">
                    {segments.data ? (
                      <Tracks segments={segments.data} prediction={prediction.data ?? null} topics={features.data?.topics ?? []} flags={flags} edits={edits} onPickFlag={pickFlag} lanes={hasScores ? laneMode : "structure"} />
                    ) : segments.isError ? (
                      <ErrorBox error={segments.error} title="Couldn't load segments" />
                    ) : (
                      <Spinner label="Loading segments" />
                    )}
                  </div>
                  {prediction.data && (
                    <p className="mt-auto flex flex-wrap items-center gap-x-2 px-1 pt-1 text-[11px] leading-snug text-ink-3">
                      <span>{prediction.data.label}</span>
                      <span aria-hidden>·</span>
                      <span className="shrink-0">model {prediction.data.model_version}</span>
                      <span aria-hidden>·</span>
                      <span className="shrink-0 tabular-nums">{mmss(duration)}</span>
                    </p>
                  )}
                </div>
              ) : shelfTab === "edits" ? (
                <EditPlan project={p} edits={edits} />
              ) : (
                <PromiseLedger ledger={flagsQ.data?.ledger} flags={flags} />
              )}
            </div>
          </section>
        </div>
      </div>
    </TimelineContext.Provider>
  );
}
