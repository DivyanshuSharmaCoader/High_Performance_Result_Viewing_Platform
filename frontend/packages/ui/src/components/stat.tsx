import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export function StatTile({
  label,
  value,
  hint,
  icon,
  trend,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  trend?: { label: string; tone: "up" | "down" | "flat" };
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-border bg-surface px-5 py-4 shadow-xs", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-medium text-fg-subtle">{label}</p>
        {icon && <span className="text-fg-subtle [&_svg]:size-4">{icon}</span>}
      </div>
      <p className="tabular mt-2 text-[26px] font-semibold leading-8 tracking-[-0.02em] text-fg">{value}</p>
      {(hint || trend) && (
        <div className="mt-1 flex items-center gap-2 text-[13px] text-fg-subtle">
          {trend && (
            <span
              className={cn(
                "font-medium",
                trend.tone === "up" && "text-success",
                trend.tone === "down" && "text-danger",
              )}
            >
              {trend.label}
            </span>
          )}
          {hint}
        </div>
      )}
    </div>
  );
}

/** Usage meter for plan limits (docs/09 LimitBanner). */
export function Meter({
  value,
  max,
  label,
  formatValue = (n) => n.toLocaleString(),
}: {
  value: number;
  max: number | null;
  label: ReactNode;
  formatValue?: (n: number) => string;
}) {
  const pct = max ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const tone = !max ? "bg-brand" : pct >= 100 ? "bg-danger-solid" : pct >= 85 ? "bg-warning" : "bg-brand";
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[13px]">
        <span className="font-medium text-fg">{label}</span>
        <span className="tabular text-fg-subtle">
          {formatValue(value)} {max === null ? "· Unlimited" : `of ${formatValue(max)}`}
        </span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-surface-3"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={max ?? undefined}
        aria-valuenow={value}
        aria-label={typeof label === "string" ? label : undefined}
      >
        {max !== null && (
          <div
            className={cn("h-full rounded-full transition-[width] duration-500", tone)}
            style={{ width: `${Math.max(pct, value > 0 ? 2 : 0)}%` }}
          />
        )}
      </div>
    </div>
  );
}

export function ProgressBar({
  value,
  className,
  label,
}: {
  value: number;
  className?: string;
  label: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("h-1.5 overflow-hidden rounded-full bg-surface-3", className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-label={label}
    >
      <div
        className="h-full rounded-full bg-brand transition-[width] duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
