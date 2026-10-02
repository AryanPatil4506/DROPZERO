import { useEffect, useMemo, useRef } from "react";
import type { Flag, TextFeatures, Transcript } from "../../api/types";
import { mmss } from "../../lib/format";
import { EstimatedBadge } from "../ui";
import { overlaps, useTimeline } from "./timeline-context";

const norm = (w: string) => w.toLocaleLowerCase().replace(/[^\p{L}\p{M}\p{N}']/gu, "");

/** Timestamped transcript. Current line highlighted, click to seek, flagged ranges underlined. */
export default function TranscriptPanel({
  transcript,
  features,
  flags,
  large = false,
}: {
  transcript: Transcript;
  features: TextFeatures | null;
  flags: Flag[];
  large?: boolean;
}) {
  const { time, seek, cut, selectedFlagId, skipRanges } = useTimeline();
  const listRef = useRef<HTMLOListElement>(null);

  const current = transcript.sentences.findIndex((s, i) => {
    const next = transcript.sentences[i + 1];
    return time >= s.start && (next ? time < next.start : time <= transcript.duration_s);
  });

  // Filler words per segment come from the text features; highlight them like syntax.
  const fillersFor = useMemo(() => {
    const segs = features?.segments ?? [];
    return (start: number) => {
      const seg = segs.find((s) => start >= s.start && start < s.end);
      return new Set((seg?.fillers ?? []).filter((f) => !f.includes(" ")).map(norm));
    };
  }, [features]);

  useEffect(() => {
    const list = listRef.current;
    const el = list?.querySelector<HTMLElement>(`[data-idx="${current}"]`);
    if (!list || !el) return;
    const top = el.offsetTop - list.clientHeight / 3;
    list.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, [current]);

  return (
    <section className="glass flex h-full min-h-0 flex-col rounded-[26px]" aria-label="Transcript">
      <header className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
        <div>
          <h2 className="text-[17px] font-medium tracking-tight">{large ? "Script" : "Transcript"}</h2>
          <p className="text-xs text-ink-3">{transcript.sentences.length} lines · click a line to jump</p>
        </div>
        {transcript.timing_source === "estimated" && <EstimatedBadge />}
      </header>
      <ol ref={listRef} className="scroll-thin relative mx-3 mb-3 min-h-0 flex-1 overflow-y-auto rounded-2xl bg-black/25 py-2 font-mono text-[13px] leading-relaxed">
        {transcript.sentences.map((s, i) => {
          const flag = flags.find((f) => overlaps(f, s));
          const inCut = !!cut && overlaps(cut, s);
          const skipped = skipRanges.some((r) => s.start >= r.start - 0.05 && s.end <= r.end + 0.05);
          const isCurrent = i === current;
          const fillers = fillersFor(s.start);
          const decoration = flag
            ? `underline decoration-2 underline-offset-4 ${flag.severity === "high" ? "decoration-high/80" : "decoration-med/80"}`
            : "";
          return (
            <li key={s.idx} data-idx={i}>
              <button
                type="button"
                onClick={() => seek(s.start + 0.01)}
                aria-current={isCurrent ? "true" : undefined}
                className={`grid w-full grid-cols-[52px_1fr] gap-3 border-l-2 px-3 py-1 text-left transition-colors ${
                  isCurrent ? "border-accent bg-white/[0.07]" : "border-transparent hover:bg-white/[0.04]"
                } ${inCut ? "bg-accent/15" : ""} ${flag && flag.id === selectedFlagId ? "bg-white/[0.05]" : ""}`}
              >
                <span className="pt-px text-[11px] text-ink-3 tabular-nums">{mmss(s.start)}</span>
                <span className={`${large ? "text-[14px]" : ""} ${isCurrent ? "text-ink" : "text-ink-2"} ${skipped ? "line-through decoration-accent/80 opacity-50" : ""}`}>
                  <span className={decoration}>
                    {s.text.split(/(\s+)/).map((tok, k) =>
                      fillers.has(norm(tok)) ? (
                        <span key={k} className="text-accent" title="Filler word">
                          {tok}
                        </span>
                      ) : (
                        tok
                      ),
                    )}
                  </span>
                  {inCut && <span className="ml-2 rounded bg-accent px-1.5 py-px font-sans text-[10px] font-semibold text-[#160700]">CUT</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
