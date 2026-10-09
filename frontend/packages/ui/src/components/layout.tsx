import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
  meta,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumb?: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 pb-6 md:flex-row md:items-end md:justify-between", className)}>
      <div className="min-w-0">
        {breadcrumb && <div className="mb-2 text-[13px] text-fg-subtle">{breadcrumb}</div>}
        <h1 className="text-[22px] font-semibold leading-8 tracking-[-0.01em] text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-subtle">{description}</p>}
        {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A titled section of a page (settings groups, detail blocks). */
export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-surface shadow-xs", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold text-fg">{title}</h2>}
            {description && <p className="mt-0.5 text-[13px] leading-5 text-fg-subtle">{description}</p>}
          </div>
          {/* Actions wrap onto their own line when the header is narrow (phones). */}
          {actions && <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="px-5 py-5">{children}</div>
    </section>
  );
}

/** Two-column settings row: label/description on the left, control on the right. */
export function SettingRow({
  label,
  description,
  children,
  labelFor,
}: {
  label: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** The id of the row's one form control (a select or input): the label names it. */
  labelFor?: string;
}) {
  return (
    <div className="grid gap-3 py-5 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,280px)_1fr] md:gap-8">
      <div>
        {labelFor ? (
          <label htmlFor={labelFor} className="block text-sm font-medium text-fg">
            {label}
          </label>
        ) : (
          <p className="text-sm font-medium text-fg">{label}</p>
        )}
        {description && <p className="mt-1 text-[13px] leading-5 text-fg-subtle">{description}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-4 flex flex-wrap items-center gap-2", className)}>{children}</div>;
}

export function DescriptionList({
  items,
  className,
}: {
  items: { term: ReactNode; detail: ReactNode }[];
  className?: string;
}) {
  return (
    <dl className={cn("grid gap-x-6 gap-y-4 sm:grid-cols-2", className)}>
      {items.map((item, i) => (
        <div key={i} className="min-w-0">
          <dt className="text-[13px] text-fg-subtle">{item.term}</dt>
          <dd className="mt-0.5 truncate text-sm font-medium text-fg">{item.detail}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-surface-2 px-1 font-mono text-[11px] text-fg-muted">
      {children}
    </kbd>
  );
}
