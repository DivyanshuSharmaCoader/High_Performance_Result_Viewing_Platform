import { buttonClasses } from "@scorecode/ui";
import {
  ArrowRight,
  BadgeCheck,
  Building2,
  CalendarClock,
  FileSpreadsheet,
  GraduationCap,
  LockKeyhole,
  QrCode,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { Link } from "react-router";

const STEPS = [
  {
    icon: FileSpreadsheet,
    title: "Import from the spreadsheets you already use",
    body: "Upload Excel or CSV in your own layout. Map columns once and ScoreCode remembers. Every problem is reported by row and column — before anything touches live marks.",
  },
  {
    icon: ShieldCheck,
    title: "Catch mistakes before students do",
    body: "Out-of-range marks, shifted rows, duplicate roll numbers and totals that don't add up are flagged with plain-language fixes and a downloadable error report.",
  },
  {
    icon: CalendarClock,
    title: "Approve and publish — now or at 10:00 sharp",
    body: "Preview results with anomaly checks, approve with an audit trail, and publish instantly or on a schedule. Corrections create a new version; nothing is silently overwritten.",
  },
  {
    icon: QrCode,
    title: "Verifiable marksheets",
    body: "Every marksheet carries a QR code that anyone — an employer, another college — can scan to confirm it's genuine and current.",
  },
];

const FEATURES = [
  {
    icon: GraduationCap,
    title: "Built for every grading model",
    body: "Percentage bands for schools, credit-based SGPA for colleges, marks and ranks for coaching.",
  },
  {
    icon: Users,
    title: "Faculty enter only their papers",
    body: "Assignments by paper and section, a keyboard-first marks grid, submit-for-review workflow.",
  },
  {
    icon: Building2,
    title: "Your brand, your portal",
    body: "Students sign in at your own address with your logo and colours.",
  },
  {
    icon: ScrollText,
    title: "Every change is audited",
    body: "Who changed which mark, when, from what to what — in an append-only log.",
  },
  {
    icon: LockKeyhole,
    title: "Isolation by design",
    body: "Each institution's data is separated in the database itself, not just in application code.",
  },
  {
    icon: BadgeCheck,
    title: "Students activate in advance",
    body: "Activation codes instead of date-of-birth passwords, so result day isn't login day.",
  },
];

const PLANS = [
  {
    name: "Free",
    detail: "Up to 150 students · 3 staff",
    note: "Full publish flow, import and verifiable marksheets",
  },
  { name: "Starter", detail: "Up to 600 students · 15 staff", note: "Your colours and login page" },
  {
    name: "Growth",
    detail: "Up to 2,000 students · 60 staff",
    note: "Departments, scheduled publication, two-person approval",
  },
  {
    name: "Pro",
    detail: "Up to 5,000 students · 200 staff",
    note: "Custom domain, API access, no ScoreCode branding",
  },
];

export default function HomePage() {
  return (
    <>
      <section className="relative overflow-hidden border-b border-border">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,color-mix(in_oklab,var(--sc-brand)_10%,transparent),transparent)]"
        />
        <div className="relative mx-auto max-w-6xl px-5 pb-20 pt-16 sm:pt-24 lg:pb-28">
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-[13px] font-medium text-fg-muted shadow-xs">
            <Sparkles className="size-3.5 text-brand-ink" aria-hidden /> For schools, colleges and coaching
            institutes
          </p>
          <h1 className="mt-6 max-w-3xl text-4xl font-semibold leading-[1.08] tracking-[-0.03em] text-fg sm:text-[56px]">
            Results your students can trust, published without the spreadsheet panic.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-fg-muted">
            ScoreCode turns your marks spreadsheets into validated, approved and verifiable results — on a
            branded portal designed to stay calm when every student checks at once.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link to="/signup" className={buttonClasses("primary", "lg")}>
              Create your institution's portal <ArrowRight />
            </Link>
            <a href="#how-it-works" className={buttonClasses("secondary", "lg")}>
              See how it works
            </a>
          </div>
          <p className="mt-4 text-[13px] text-fg-subtle">Free for up to 150 students. No card required.</p>
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20 lg:py-28">
        <p className="text-[13px] font-semibold uppercase tracking-[0.08em] text-brand-ink">How it works</p>
        <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-[-0.02em]">
          From marks spreadsheet to verified marksheet
        </h2>
        <ol className="mt-12 grid gap-x-10 gap-y-12 md:grid-cols-2">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-5">
              <div className="flex flex-col items-center">
                <span className="flex size-10 items-center justify-center rounded-xl border border-border bg-surface text-brand-ink shadow-xs">
                  <s.icon className="size-5" aria-hidden />
                </span>
                {i < STEPS.length - 1 && (
                  <span aria-hidden className="mt-3 w-px flex-1 bg-border md:hidden" />
                )}
              </div>
              <div>
                <p className="text-[13px] font-medium text-fg-subtle">Step {i + 1}</p>
                <h3 className="mt-1 text-lg font-semibold tracking-[-0.01em]">{s.title}</h3>
                <p className="mt-2 text-[15px] leading-7 text-fg-muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-y border-border bg-surface">
        <div className="mx-auto max-w-6xl px-5 py-20 lg:py-24">
          <h2 className="max-w-2xl text-3xl font-semibold tracking-[-0.02em]">
            Everything a results office needs — nothing it doesn't
          </h2>
          <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="bg-surface p-6">
                <f.icon className="size-5 text-brand-ink" aria-hidden />
                <h3 className="mt-4 text-[15px] font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-sm leading-6 text-fg-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="plans" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20 lg:py-28">
        <h2 className="text-3xl font-semibold tracking-[-0.02em]">Plans that grow with you</h2>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-fg-muted">
          Every plan includes spreadsheet import, verifiable marksheets and the audit log. Paid plans are
          billed annually; we're onboarding early institutions personally — write to us for pricing.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((p) => (
            <div
              key={p.name}
              className="flex flex-col rounded-xl border border-border bg-surface p-5 shadow-xs"
            >
              <h3 className="text-base font-semibold">{p.name}</h3>
              <p className="mt-2 text-sm font-medium text-fg">{p.detail}</p>
              <p className="mt-1 text-sm leading-6 text-fg-muted">{p.note}</p>
            </div>
          ))}
        </div>
        <p className="mt-6 text-[13px] text-fg-subtle">
          Universities and multi-campus groups: Enterprise plans with custom limits and dedicated deployments
          are available.
        </p>
      </section>

      <section className="border-t border-border bg-[#1e1b4b] text-white">
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-5 py-16 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-[-0.02em]">Set up your portal in minutes</h2>
            <p className="mt-2 text-[15px] text-white/75">
              Start free, import your students, and publish your first result.
            </p>
          </div>
          <Link
            to="/signup"
            className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-5 text-[15px] font-semibold text-[#1e1b4b] hover:bg-white/90"
          >
            Get started <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>
    </>
  );
}
