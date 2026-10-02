import type { RefObject } from "react";
import type { Transcript } from "../../api/types";
import { useTimeline } from "./timeline-context";

/**
 * Full-bleed background. Plays the project's video when there is one; script projects (no media)
 * get a teleprompter of the current line over an ambient backdrop.
 */
export default function BackgroundStage({
  src,
  videoRef,
  transcript,
  onTime,
  onPlayState,
  onError,
}: {
  src: string | null;
  videoRef: RefObject<HTMLVideoElement>;
  transcript: Transcript | null;
  onTime: (t: number) => void;
  onPlayState: (playing: boolean) => void;
  onError: () => void;
}) {
  const { time, playing, setPlaying } = useTimeline();
  const sentences = transcript?.sentences ?? [];
  const idx = sentences.findIndex((s, i) => time >= s.start && (i === sentences.length - 1 || time < sentences[i + 1].start));

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#050506]">
      {src ? (
        <video
          ref={videoRef}
          key={src}
          src={src}
          className="h-full w-full object-cover"
          preload="metadata"
          playsInline
          onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)}
          onSeeked={(e) => onTime(e.currentTarget.currentTime)}
          onPlay={() => onPlayState(true)}
          onPause={() => onPlayState(false)}
          onEnded={() => onPlayState(false)}
          onError={onError}
          onClick={() => setPlaying(!playing)}
        />
      ) : (
        <div
          className="flex h-full w-full items-start justify-center pt-[16vh] bg-[radial-gradient(60%_55%_at_62%_38%,rgba(255,91,31,0.35),transparent_65%),radial-gradient(45%_45%_at_85%_80%,rgba(239,63,67,0.22),transparent_70%),radial-gradient(50%_50%_at_30%_10%,rgba(106,143,224,0.12),transparent_70%),#070708]"
          onClick={() => setPlaying(!playing)}
        >
          {idx >= 0 && (
            <div className="pointer-events-none w-[min(600px,36vw)] -translate-x-[2%] space-y-4 text-center" aria-hidden>
              <p className="text-[15px] text-white/30">{sentences[idx - 1]?.text}</p>
              <p className="text-[clamp(20px,2.1vw,36px)] leading-tight font-medium tracking-tight text-white/90 [text-shadow:0_4px_30px_rgba(0,0,0,0.6)]">
                {sentences[idx].text}
              </p>
              <p className="text-[15px] text-white/30">{sentences[idx + 1]?.text}</p>
            </div>
          )}
        </div>
      )}
      {/* vignettes keep the floating panels legible over any footage */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(5,5,6,0.85)_0%,rgba(5,5,6,0.25)_32%,transparent_55%,rgba(5,5,6,0.35)_78%,rgba(5,5,6,0.8)_100%)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[45%] bg-[linear-gradient(0deg,rgba(5,5,6,0.95),transparent)]" />
    </div>
  );
}
