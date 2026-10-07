import { cn } from "@scorecode/ui";
import { Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router";

import { useTrial } from "./api";

const KEY = "sc:trial-banner-dismissed";

function wasDismissed(day: number): boolean {
  try {
    return sessionStorage.getItem(KEY) === String(day);
  } catch {
    return false; // storage blocked: just show it
  }
}

/** A quiet line above every staff page while the trial runs; amber in its last week. */
export function TrialBanner() {
  const trial = useTrial();
  const location = useLocation();
  const left = trial?.state === "active" ? trial.days_left : null;
  const [dismissed, setDismissed] = useState(false);
  // Hidden for the rest of the day it was dismissed (per tab), shown again when the count moves.
  if (left === null || dismissed || wasDismissed(left) || location.pathname === "/admin/plan") return null;
  const urgent = left <= 7;
  return (
    <div
      role="status"
      className={cn(
        "mb-5 flex items-center gap-3 rounded-xl border px-4 py-2.5 text-[13px] animate-fade-in",
        urgent ? "border-warning-border bg-warning-soft text-fg" : "border-brand/20 bg-brand-soft/50 text-fg",
      )}
    >
      <Sparkles className={cn("size-4 shrink-0", urgent ? "text-warning" : "text-brand-ink")} aria-hidden />
      <p className="min-w-0 flex-1">
        <span className="font-medium">
          {left === 0
            ? "Your Pro trial ends today."
            : `Pro trial: ${left} ${left === 1 ? "day" : "days"} left.`}
        </span>{" "}
        <span className="text-fg-muted">
          {urgent ? "Afterwards you're back on Free — nothing is deleted." : "Every Pro feature is on."}
        </span>
      </p>
      <Link to="/admin/plan" className="shrink-0 font-medium text-brand-ink hover:underline">
        {urgent ? "Keep Pro" : "Details"}
      </Link>
      <button
        type="button"
        aria-label="Hide for now"
        className="-mr-1 rounded-md p-1 text-fg-subtle hover:bg-surface-2 hover:text-fg"
        onClick={() => {
          try {
            sessionStorage.setItem(KEY, String(left));
          } catch {
            /* fine: hidden until reload */
          }
          setDismissed(true);
        }}
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
