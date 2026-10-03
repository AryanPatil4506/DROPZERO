import type { ReactNode } from "react";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 text-sm text-ink-2">
      <span className="size-4 animate-spin rounded-full border-2 border-white/20 border-t-accent" aria-hidden />
      {label}…
    </div>
  );
}

export function ErrorBox({ error, title = "Couldn't load this" }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-2xl border border-high/30 bg-high/10 px-4 py-3 text-sm">
      <p className="font-medium text-ink">{title}</p>
      <p className="mt-1 text-[#ffb3b4]">{message}</p>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line-2 px-5 py-6 text-sm text-ink-2">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-1">{children}</div>}
    </div>
  );
}

export function EstimatedBadge() {
  return (
    <span className="chip border-med/40 text-[#f6d391]" title="Script mode: times are estimated from word counts, not measured from audio.">
      Estimated timing
    </span>
  );
}

export function MockBadge({ note }: { note?: string }) {
  if (!note) return null;
  return (
    <span className="chip border-med/40 bg-med/10 text-[#f6d391]" title={note}>
      Mock · placeholder numbers
    </span>
  );
}

export function SeverityTag({ severity }: { severity: "high" | "medium" | "low" }) {
  const color = severity === "high" ? "bg-high" : severity === "medium" ? "bg-med" : "bg-ink-3";
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-ink uppercase">
      <span className={`size-2 rounded-full ${color}`} aria-hidden />
      {severity === "medium" ? "Medium" : severity === "high" ? "High" : "Low"}
    </span>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full flex-wrap gap-y-1 rounded-[20px] bg-white/5 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={`h-8 rounded-full px-3.5 text-[13px] font-medium transition-colors ${
            o.value === value ? "bg-accent text-[#160700]" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
