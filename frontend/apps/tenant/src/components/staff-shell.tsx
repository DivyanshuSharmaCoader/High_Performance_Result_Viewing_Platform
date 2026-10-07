import {
  Avatar,
  Badge,
  Menu,
  MenuContent,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
  Sheet,
  SheetContent,
  TenantMark,
  cn,
  useColorScheme,
} from "@scorecode/ui";
import {
  Award,
  ChevronsUpDown,
  ClipboardCheck,
  ClipboardList,
  FileSpreadsheet,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  Menu as MenuIcon,
  Monitor,
  Network,
  Moon,
  ScrollText,
  Settings,
  Sun,
  UserRound,
  Users,
  Gauge,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { TrialBanner } from "../features/plan/trial-banner";
import { useLogout, useSession } from "../lib/session";
import { useTenant } from "../lib/tenant";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  permission: string;
  end?: boolean;
}
interface NavGroup {
  label: string | null;
  items: NavItem[];
}

/** Navigation only lists pages that exist and that the signed-in user may open. */
export const NAV: NavGroup[] = [
  {
    label: null,
    items: [
      { to: "/admin", label: "Dashboard", icon: LayoutDashboard, permission: "students.view", end: true },
    ],
  },
  {
    label: "People",
    items: [
      { to: "/admin/students", label: "Students", icon: GraduationCap, permission: "students.view" },
      { to: "/admin/staff", label: "Staff", icon: Users, permission: "staff.view" },
      { to: "/admin/imports", label: "Imports", icon: FileSpreadsheet, permission: "imports.manage" },
    ],
  },
  {
    label: "Examinations",
    items: [
      { to: "/admin/exams", label: "Exams", icon: ClipboardList, permission: "exams.view" },
      { to: "/marking", label: "Marks entry", icon: ClipboardCheck, permission: "exams.view_assigned" },
    ],
  },
  {
    label: "Academics",
    items: [
      { to: "/admin/academics", label: "Structure", icon: Network, permission: "academics.view" },
      { to: "/admin/grading", label: "Grading", icon: Award, permission: "grading.view" },
    ],
  },
  {
    label: "Institution",
    items: [
      { to: "/admin/settings", label: "Settings", icon: Settings, permission: "settings.manage" },
      { to: "/admin/plan", label: "Plan & usage", icon: Gauge, permission: "subscription.view" },
      { to: "/admin/audit-log", label: "Audit log", icon: ScrollText, permission: "audit.view" },
    ],
  },
];

const ROLE_LABEL: Record<string, string> = {
  institution_owner: "Owner",
  institution_admin: "Administrator",
  faculty: "Faculty",
  student: "Student",
};

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const me = useSession();
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {NAV.map((group, gi) => {
        const items = group.items.filter((i) => me.permissions.includes(i.permission));
        if (items.length === 0) return null;
        return (
          <div key={gi}>
            {group.label && (
              <p className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-fg-subtle">
                {group.label}
              </p>
            )}
            <ul className="flex flex-col gap-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end ?? false}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13.5px] font-medium transition-colors",
                        isActive
                          ? "bg-brand-soft text-brand-ink"
                          : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <item.icon
                          className={cn(
                            "size-4 shrink-0",
                            isActive ? "text-brand-ink" : "text-fg-subtle group-hover:text-fg-muted",
                          )}
                          aria-hidden
                        />
                        {item.label}
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function TenantHeader() {
  const tenant = useTenant();
  const me = useSession();
  const b = tenant.branding;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2.5 px-1">
      <TenantMark
        name={b.display_name}
        logoUrl={b.logo_url ? `${b.logo_url}?v=${b.logo_version}` : null}
        size={32}
      />
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-[13px] font-semibold leading-4 text-fg" title={b.display_name}>
          {b.short_name ?? b.display_name}
        </p>
        <p className="mt-0.5 truncate text-xs text-fg-subtle">{me.plan.name} plan</p>
      </div>
    </div>
  );
}

function UserMenu({ compact }: { compact?: boolean }) {
  const me = useSession();
  const logout = useLogout();
  const navigate = useNavigate();
  const [scheme, setScheme] = useColorScheme();
  const role = me.roles.map((r) => ROLE_LABEL[r] ?? r).join(", ");
  return (
    <Menu>
      <MenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex items-center gap-2.5 rounded-lg text-left transition-colors hover:bg-surface-2",
            compact ? "p-1" : "w-full p-2",
          )}
          aria-label="Account menu"
        >
          <Avatar name={me.full_name} size={compact ? "sm" : "md"} />
          {!compact && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-fg">{me.full_name}</span>
                <span className="block truncate text-xs text-fg-subtle">{role}</span>
              </span>
              <ChevronsUpDown className="size-4 text-fg-subtle" aria-hidden />
            </>
          )}
        </button>
      </MenuTrigger>
      <MenuContent align={compact ? "end" : "start"} className="w-60">
        <MenuLabel>
          <span className="block truncate text-fg">{me.full_name}</span>
          <span className="block truncate font-normal">{me.email ?? me.login_id}</span>
        </MenuLabel>
        <MenuSeparator />
        <MenuItem icon={<UserRound />} onSelect={() => void navigate("/account")}>
          Account & security
        </MenuItem>
        <MenuSeparator />
        <MenuLabel>Appearance</MenuLabel>
        <MenuItem
          icon={<Sun />}
          onSelect={() => setScheme("light")}
          shortcut={scheme === "light" ? "✓" : undefined}
        >
          Light
        </MenuItem>
        <MenuItem
          icon={<Moon />}
          onSelect={() => setScheme("dark")}
          shortcut={scheme === "dark" ? "✓" : undefined}
        >
          Dark
        </MenuItem>
        <MenuItem
          icon={<Monitor />}
          onSelect={() => setScheme("system")}
          shortcut={scheme === "system" ? "✓" : undefined}
        >
          System
        </MenuItem>
        <MenuSeparator />
        <MenuItem icon={<LogOut />} onSelect={() => logout.mutate()}>
          Sign out
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

export function StaffShell({ children }: { children?: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const tenant = useTenant();
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-surface lg:flex">
        <div className="flex h-16 items-center border-b border-border px-4">
          <TenantHeader />
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-5">
          <NavList />
        </div>
        <div className="border-t border-border p-2">
          <UserMenu />
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="-ml-1 rounded-md p-2 text-fg-muted hover:bg-surface-2"
          aria-label="Open navigation"
        >
          <MenuIcon className="size-5" />
        </button>
        <span className="truncate text-sm font-semibold">
          {tenant.branding.short_name ?? tenant.branding.display_name}
        </span>
        <UserMenu compact />
      </header>
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent title={<TenantHeader />} side="left" className="max-w-[300px]">
          <NavList onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <main
        id="main"
        key={location.pathname}
        className="min-w-0 animate-fade-in px-4 py-6 sm:px-6 lg:px-10 lg:py-8"
      >
        <div className="mx-auto max-w-6xl">
          <TrialBanner />
          {children ?? <Outlet />}
        </div>
      </main>
    </div>
  );
}

export function PlanBadge() {
  const me = useSession();
  return <Badge tone="brand">{me.plan.name}</Badge>;
}
