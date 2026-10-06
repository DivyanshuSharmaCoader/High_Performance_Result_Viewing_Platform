import { Checkbox as C, Switch as S } from "radix-ui";
import { Check, Minus } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export function Checkbox({
  checked,
  onCheckedChange,
  label,
  description,
  disabled,
  id,
}: {
  checked: boolean | "indeterminate";
  onCheckedChange: (checked: boolean) => void;
  label?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
}) {
  const box = (
    <C.Root
      id={id}
      checked={checked}
      disabled={disabled}
      onCheckedChange={(v) => onCheckedChange(v === true)}
      className={cn(
        "flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-border-strong bg-surface shadow-xs",
        "data-[state=checked]:border-brand data-[state=checked]:bg-brand data-[state=indeterminate]:border-brand data-[state=indeterminate]:bg-brand",
        "disabled:opacity-50",
      )}
      aria-label={typeof label === "string" ? label : undefined}
    >
      <C.Indicator className="text-brand-fg">
        {checked === "indeterminate" ? (
          <Minus className="size-3" strokeWidth={3} />
        ) : (
          <Check className="size-3" strokeWidth={3} />
        )}
      </C.Indicator>
    </C.Root>
  );
  if (!label) return box;
  return (
    <label className={cn("flex items-start gap-3", disabled ? "opacity-60" : "cursor-pointer")}>
      <span className="mt-0.5">{box}</span>
      <span>
        <span className="block text-sm font-medium text-fg">{label}</span>
        {description && (
          <span className="mt-0.5 block text-[13px] leading-5 text-fg-subtle">{description}</span>
        )}
      </span>
    </label>
  );
}

export function Switch({
  checked,
  onCheckedChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      className={cn("flex items-start justify-between gap-6", disabled ? "opacity-60" : "cursor-pointer")}
    >
      <span>
        <span className="block text-sm font-medium text-fg">{label}</span>
        {description && (
          <span className="mt-0.5 block text-[13px] leading-5 text-fg-subtle">{description}</span>
        )}
      </span>
      <S.Root
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-surface-3 transition-colors data-[state=checked]:bg-brand"
      >
        <S.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-[18px]" />
      </S.Root>
    </label>
  );
}

/** Large radio cards (e.g. choose institution type, approval mode). */
export function RadioCards<V extends string>({
  value,
  onChange,
  options,
  name,
  columns = 2,
}: {
  value: V;
  onChange: (value: V) => void;
  options: {
    value: V;
    label: ReactNode;
    description?: ReactNode;
    icon?: ReactNode;
    disabled?: boolean;
    badge?: ReactNode;
  }[];
  name: string;
  columns?: 1 | 2 | 3;
}) {
  return (
    <div
      role="radiogroup"
      className={cn("grid gap-2", columns === 2 && "sm:grid-cols-2", columns === 3 && "sm:grid-cols-3")}
    >
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <label
            key={o.value}
            className={cn(
              "relative flex gap-3 rounded-lg border bg-surface p-3.5 transition-[border-color,box-shadow]",
              selected ? "border-brand ring-[3px] ring-brand/15" : "border-border hover:border-border-strong",
              o.disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
            )}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={selected}
              disabled={o.disabled}
              onChange={() => onChange(o.value)}
              className="sr-only"
            />
            {o.icon && <span className="mt-0.5 text-fg-subtle [&_svg]:size-[18px]">{o.icon}</span>}
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-sm font-medium text-fg">
                {o.label}
                {o.badge}
              </span>
              {o.description && (
                <span className="mt-0.5 block text-[13px] leading-5 text-fg-subtle">{o.description}</span>
              )}
            </span>
            <span
              aria-hidden
              className={cn(
                "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
                selected ? "border-brand bg-brand" : "border-border-strong",
              )}
            >
              {selected && <span className="size-1.5 rounded-full bg-brand-fg" />}
            </span>
          </label>
        );
      })}
    </div>
  );
}
