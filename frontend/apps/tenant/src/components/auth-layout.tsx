import { TenantMark } from "@scorecode/ui";
import { BadgeCheck, LockKeyhole, Smartphone } from "lucide-react";
import type { ReactNode } from "react";

import { useTenant } from "../lib/tenant";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const tenant = useTenant();
  const b = tenant.branding;
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <main className="flex flex-col px-5 py-8 sm:px-10 lg:px-16">
        <div className="flex items-center gap-3">
          <TenantMark
            name={b.display_name}
            logoUrl={b.logo_url ? `${b.logo_url}?v=${b.logo_version}` : null}
            size={36}
          />
          <span className="text-[15px] font-semibold leading-5 text-fg">{b.display_name}</span>
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-12">
          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-fg">{title}</h1>
          {subtitle && <p className="mt-2 text-sm leading-6 text-fg-subtle">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 text-sm text-fg-subtle">{footer}</div>}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-2 text-xs text-fg-subtle">
          <span>{b.footer_text ?? `© ${new Date().getFullYear()} ${tenant.tenant.name}`}</span>
          {b.show_powered_by && (
            <span>
              Powered by <span className="font-semibold text-fg-muted">ScoreCode</span>
            </span>
          )}
        </footer>
      </main>
      <aside className="relative hidden overflow-hidden border-l border-border bg-brand-soft lg:flex lg:flex-col lg:justify-between lg:p-14">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-32 -top-32 size-[520px] rounded-full border-[56px] border-brand/[0.07]"
        />
        <div className="relative max-w-md">
          <p className="text-[13px] font-semibold uppercase tracking-[0.08em] text-brand-ink">
            Results portal
          </p>
          <h2 className="mt-4 text-[32px] font-semibold leading-[1.15] tracking-[-0.02em] text-fg">
            {b.login_heading ?? `Welcome to ${b.display_name}`}
          </h2>
          <p className="mt-4 text-[15px] leading-7 text-fg-muted">
            {b.login_message ??
              "Sign in to see your published results, download marksheets and stay up to date with announcements from your institution."}
          </p>
        </div>
        <ul className="relative grid max-w-md gap-4 text-sm text-fg-muted">
          <li className="flex gap-3">
            <BadgeCheck className="mt-0.5 size-5 shrink-0 text-brand-ink" aria-hidden />
            Every marksheet carries a QR code anyone can scan to verify it's genuine.
          </li>
          <li className="flex gap-3">
            <Smartphone className="mt-0.5 size-5 shrink-0 text-brand-ink" aria-hidden />
            Works on any phone — no app to install.
          </li>
          <li className="flex gap-3">
            <LockKeyhole className="mt-0.5 size-5 shrink-0 text-brand-ink" aria-hidden />
            Your results are visible only to you and your institution.
          </li>
        </ul>
      </aside>
    </div>
  );
}
