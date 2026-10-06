import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export function Stepper({ steps, current }: { steps: { label: ReactNode }[]; current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-[13px]">
      {steps.map((step, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li
            key={i}
            className="flex items-center gap-2"
            aria-current={state === "current" ? "step" : undefined}
          >
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full text-xs font-semibold",
                state === "done" && "bg-brand text-brand-fg",
                state === "current" && "bg-brand-soft text-brand-ink ring-2 ring-brand",
                state === "todo" && "bg-surface-2 text-fg-subtle ring-1 ring-border",
              )}
            >
              {state === "done" ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
            </span>
            <span className={cn("font-medium", state === "todo" ? "text-fg-subtle" : "text-fg")}>
              {step.label}
            </span>
            {i < steps.length - 1 && <span aria-hidden className="mx-1 h-px w-6 bg-border-strong sm:w-10" />}
          </li>
        );
      })}
    </ol>
  );
}
