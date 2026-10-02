import { mmss } from "../../lib/format";
import { IconBack10, IconFwd10, IconPause, IconPlay, IconRestart, IconScissors } from "../icons";
import { useTimeline } from "./timeline-context";

/** Floating transport, as in the reference: restart · −10 · play/pause · +10 · edited preview. */
export default function PlaybackCapsule({ className = "" }: { className?: string }) {
  const { time, duration, seek, playing, setPlaying, restart, previewEdited, setPreviewEdited, skipRanges } = useTimeline();
  const side = "grid size-11 place-items-center rounded-full bg-white/[0.07] text-ink-2 transition-colors hover:bg-white/[0.12] hover:text-ink";
  return (
    <div className={`glass flex items-center gap-1.5 rounded-full p-1.5 ${className}`}>
      <button type="button" aria-label="Restart from 00:00" title="Restart" onClick={restart} className={side}>
        <IconRestart className="size-5" />
      </button>
      <button type="button" aria-label="Back 10 seconds" onClick={() => seek(Math.max(0, time - 10))} className={side}>
        <IconBack10 className="size-5" />
      </button>
      <button
        type="button"
        aria-label={playing ? "Pause" : "Play"}
        onClick={() => setPlaying(!playing)}
        className="grid size-14 place-items-center rounded-full bg-ink text-[#0a0a0b] shadow-[0_12px_32px_-10px_rgba(255,255,255,0.55)]"
      >
        {playing ? <IconPause className="size-5" /> : <IconPlay className="size-5 translate-x-px" />}
      </button>
      <button type="button" aria-label="Forward 10 seconds" onClick={() => seek(Math.min(duration, time + 10))} className={side}>
        <IconFwd10 className="size-5" />
      </button>
      <button
        type="button"
        aria-pressed={previewEdited}
        disabled={skipRanges.length === 0}
        title={skipRanges.length === 0 ? "Accept an edit or mark a cut to preview it" : "Play with accepted cuts skipped"}
        onClick={() => setPreviewEdited(!previewEdited)}
        className={`grid size-11 place-items-center rounded-full transition-colors disabled:opacity-35 ${
          previewEdited ? "bg-accent text-[#160700]" : "bg-white/[0.07] text-ink-2 hover:text-ink"
        }`}
      >
        <IconScissors className="size-5" />
        <span className="sr-only">Preview with cuts</span>
      </button>
      <span className="px-3 text-[13px] text-ink-2 tabular-nums">
        <span className="text-ink">{mmss(time)}</span> / {mmss(duration)}
      </span>
    </div>
  );
}
