import { PageHeader, cn } from "@scorecode/ui";
import { NavLink, Outlet } from "react-router";

import { useSummary } from "./api";

const TABS = [
  { to: "/admin/academics", label: "Sessions & terms", key: "sessions", end: true },
  { to: "/admin/academics/departments", label: "Departments", key: "departments" },
  { to: "/admin/academics/programs", label: "Programs", key: "programs" },
  { to: "/admin/academics/cohorts", label: "Cohorts", key: "cohorts" },
  { to: "/admin/academics/courses", label: "Courses", key: "courses" },
] as const;

export default function AcademicsLayout() {
  const summary = useSummary();
  return (
    <>
      <PageHeader
        title="Academic structure"
        description="The sessions, programs, cohorts and courses your exams are built on. Records are archived, never deleted, so past results keep their context."
      />
      <nav
        aria-label="Academic structure"
        className="mb-6 flex gap-1 overflow-x-auto border-b border-border [scrollbar-width:none]"
      >
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={"end" in t ? t.end : false}
            className={({ isActive }) =>
              cn(
                "-mb-px inline-flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-medium transition-colors",
                isActive ? "border-brand text-fg" : "border-transparent text-fg-subtle hover:text-fg",
              )
            }
          >
            {t.label}
            {summary.data && (
              <span className="tabular rounded-full bg-surface-2 px-1.5 text-xs text-fg-muted">
                {summary.data[t.key]}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
