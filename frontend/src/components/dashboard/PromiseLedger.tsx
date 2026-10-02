import type { Flag, PromiseItem } from "../../api/types";
import { mmss } from "../../lib/format";
import { EmptyState } from "../ui";
import { useTimeline } from "./timeline-context";

const STATUS: Record<PromiseItem["status"], { label: string; dot: string; text: string }> = {
  kept: { label: "Kept on time", dot: "bg-ok", text: "text-[#7fd8b8]" },
  late: { label: "Kept late", dot: "bg-med", text: "text-[#f6d391]" },
  open: { label: "Open loop", dot: "bg-high", text: "text-[#ffb3b4]" },
};

function delayText(s: number | null): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m ? `${m} m ${String(sec).padStart(2, "0")} s` : `${sec} s`;
}

/**
 * Promise ledger: every promise made in the title or opening, when it is paid off, and whether
 * viewers had to wait too long. Rows seek the timeline; late/open promises link to their flag.
 */
export default function PromiseLedger({ ledger, flags }: { ledger: PromiseItem[] | undefined; flags: Flag[] }) {
  const { seek, selectFlag } = useTimeline();

  if (!ledger) {
    return (
      <EmptyState title="No promise ledger for this project yet">
        Re-run the analysis with the current backend to find promises in the opening and when they pay off.
      </EmptyState>
    );
  }
  if (ledger.length === 0) {
    return <EmptyState title="No promises found in the title or the opening" />;
  }

  // The backend raises a payoff_delay flag starting at the promise ("made at"); the title's
  // late-promise flag covers the opening instead. Prefer the exact start, then containment.
  const delayFlags = flags.filter((f) => f.category === "payoff_delay");
  const flagFor = (p: PromiseItem) =>
    delayFlags.find((f) => Math.abs(f.start - p.made_at) < 0.5) ??
    delayFlags.find((f) => f.start <= p.made_at + 0.5 && p.made_at < f.end + 0.5) ??
    null;

  return (
    <div className="scroll-thin h-full overflow-y-auto pr-1">
      <table className="w-full table-fixed text-left text-[13px]">
        <colgroup>
          <col />
          <col className="w-[84px]" />
          <col className="w-[96px]" />
          <col className="w-[92px]" />
          <col className="w-[180px]" />
        </colgroup>
        <thead className="sticky top-0 bg-[#141418] text-[11px] text-ink-3">
          <tr>
            <th className="py-1.5 pr-3 pl-1 font-medium">Promise</th>
            <th className="px-3 font-medium">Made at</th>
            <th className="px-3 font-medium">Paid off at</th>
            <th className="px-3 font-medium">Wait</th>
            <th className="pl-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {ledger.map((p, i) => {
            const st = STATUS[p.status];
            const flag = p.status === "kept" ? null : flagFor(p);
            return (
              <tr key={`${p.made_at}-${i}`} className="border-t border-line align-top">
                <td className="py-2 pr-3 pl-1">
                  <button
                    type="button"
                    onClick={() => seek(p.made_at)}
                    className="block w-full truncate text-left text-ink hover:underline"
                    title={p.text}
                  >
                    <span className="mr-1.5 rounded bg-white/[0.07] px-1.5 py-px text-[10px] font-semibold tracking-wide text-ink-3 uppercase">
                      {p.source === "title" ? "Title" : "Intro"}
                    </span>
                    “{p.text}”
                  </button>
                  {p.payoff_text && (
                    <p className="mt-0.5 truncate text-[12px] text-ink-3" title={p.payoff_text}>
                      Paid off by: “{p.payoff_text}”
                      {p.similarity != null && <span className="tabular-nums"> · match {p.similarity.toFixed(2)}</span>}
                    </p>
                  )}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <button type="button" onClick={() => seek(p.made_at)} className="text-ink-2 tabular-nums hover:text-ink">
                    {mmss(p.made_at)}
                  </button>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {p.payoff_at != null ? (
                    <button type="button" onClick={() => seek(p.payoff_at!)} className="text-ink-2 tabular-nums hover:text-ink">
                      {mmss(p.payoff_at)}
                    </button>
                  ) : (
                    <span className="text-ink-3">never</span>
                  )}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-ink-2 tabular-nums">{delayText(p.delay_s)}</td>
                <td className="py-2 pl-3 whitespace-nowrap">
                  <span className={`inline-flex items-center gap-1.5 ${st.text}`}>
                    <span className={`size-2 rounded-full ${st.dot}`} aria-hidden />
                    {st.label}
                  </span>
                  {flag && (
                    <button
                      type="button"
                      onClick={() => {
                        selectFlag(flag.id);
                        seek(flag.start);
                      }}
                      className="ml-2 text-[12px] text-accent hover:underline"
                    >
                      See fix
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
