import { Tabs as T } from "radix-ui";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export const Tabs = T.Root;
export const TabsContent = T.Content;

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <T.List
      className={cn("flex gap-1 overflow-x-auto border-b border-border [scrollbar-width:none]", className)}
    >
      {children}
    </T.List>
  );
}

export function TabsTrigger({
  value,
  children,
  count,
}: {
  value: string;
  children: ReactNode;
  count?: number;
}) {
  return (
    <T.Trigger
      value={value}
      className={cn(
        "relative -mb-px inline-flex h-10 items-center gap-2 whitespace-nowrap border-b-2 border-transparent px-3 text-sm font-medium text-fg-subtle",
        "transition-colors hover:text-fg data-[state=active]:border-brand data-[state=active]:text-fg",
      )}
    >
      {children}
      {count !== undefined && (
        <span className="rounded-full bg-surface-2 px-1.5 text-xs tabular-nums text-fg-muted">{count}</span>
      )}
    </T.Trigger>
  );
}

/** Segmented control for compact filters (e.g. Errors / Warnings / All). */
export function Segmented<V extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: V;
  onChange: (value: V) => void;
  options: { value: V; label: ReactNode; count?: number }[];
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 text-[13px] font-medium transition-colors",
            value === o.value ? "bg-surface text-fg shadow-xs" : "text-fg-subtle hover:text-fg",
          )}
        >
          {o.label}
          {o.count !== undefined && <span className="tabular-nums text-fg-subtle">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
