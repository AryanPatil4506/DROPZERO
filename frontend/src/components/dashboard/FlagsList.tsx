import { useState } from "react";
import type { Flag } from "../../api/types";
import { FLAG_CATEGORY_LABEL, mmss } from "../../lib/format";
import { Segmented } from "../ui";
import { useTimeline } from "./timeline-context";

export default function FlagsList({ flags }: { flags: Flag[] }) {
  const [sort, setSort] = useState<"time" | "severity">("time");
  const { selectedFlagId, selectFlag, seek } = useTimeline();
  const sorted = [...flags].sort((a, b) =>
    sort === "time" ? a.start - b.start : b.risk_score - a.risk_score || a.start - b.start,
  );

  return (
    <section className="glass rounded-[26px] p-4" aria-label="Flags">
      <div className="flex items-center justify-between gap-2 px-1">
        <h2 className="text-[15px] font-medium">
          Flags <span className="text-ink-3">({flags.length})</span>
        </h2>
        <Segmented
          label="Sort flags"
          value={sort}
          onChange={setSort}
          options={[
            { value: "time", label: "Time" },
            { value: "severity", label: "Severity" },
          ]}
        />
      </div>
      <ul className="mt-3 space-y-1.5">
        {sorted.map((f) => (
          <li key={f.id}>
            <button
              type="button"
              onClick={() => {
                selectFlag(f.id);
                seek(f.start);
              }}
              aria-pressed={f.id === selectedFlagId}
              className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2 text-left transition-colors ${
                f.id === selectedFlagId ? "bg-ink text-[#0a0a0b]" : "bg-white/[0.04] hover:bg-white/[0.08]"
              }`}
            >
              <span className={`size-2.5 shrink-0 rounded-full ${f.severity === "high" ? "bg-high" : "bg-med"}`} aria-hidden />
              <span className="w-[86px] shrink-0 text-xs tabular-nums opacity-80">
                {mmss(f.start)}–{mmss(f.end)}
              </span>
              <span className="min-w-0 flex-1 truncate text-[13px]">
                <span className="sr-only">{f.severity} severity. </span>
                {FLAG_CATEGORY_LABEL[f.category] ?? f.category}
                {f.source && <span className="ml-1.5 text-[11px] opacity-60">· {f.source === "rule" ? "rule" : f.source === "model" ? "model" : "model + rule"}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
