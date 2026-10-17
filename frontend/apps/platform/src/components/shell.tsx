import {
  Avatar,
  Badge,
  Menu,
  MenuContent,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
  cn,
  useColorScheme,
} from "@scorecode/ui";
import { Activity, Building2, Gauge, Layers, LogOut, Moon, ScrollText, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useLogout, usePlatformMe } from "../lib/session";

const NAV = [
  { to: "/", label: "Overview", icon: Gauge, end: true, permission: "platform.health.view" },
  { to: "/tenants", label: "Institutions", icon: Building2, permission: "platform.tenants.view" },
  { to: "/plans", label: "Plans & features", icon: Layers, permission: "platform.tenants.view" },
  { to: "/health", label: "System health", icon: Activity, permission: "platform.health.view" },
  { to: "/audit", label: "Platform audit log", icon: ScrollText, permission: "platform.audit.view" },
];

export function Shell() {
  const me = usePlatformMe().data!;
  const logout = useLogout();
  const [scheme, setScheme] = useColorScheme();
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[232px_minmax(0,1fr)]">
      <aside className="flex flex-col border-b border-border bg-surface md:sticky md:top-0 md:h-dvh md:border-b-0 md:border-r">
        <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
          <span className="flex size-7 items-center justify-center rounded-md bg-white">
            <img src="/logo-mark.png" alt="" className="size-5" width={20} height={20} />
          </span>
          <span className="text-sm font-semibold">ScoreCode</span>
          <Badge tone="info" className="ml-auto">
            Console
          </Badge>
        </div>
        <nav
          aria-label="Console"
          className="flex gap-1 overflow-x-auto px-3 py-3 md:flex-1 md:flex-col md:overflow-visible md:py-5"
        >
          {NAV.filter((n) => me.permissions.includes(n.permission)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end ?? false}
              className={({ isActive }) =>
                cn(
                  "flex h-8 shrink-0 items-center gap-2.5 rounded-md px-2.5 text-[13.5px] font-medium transition-colors",
                  isActive ? "bg-surface-2 text-fg" : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                )
              }
            >
              <n.icon className="size-4 text-fg-subtle" aria-hidden />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t border-border p-2 md:block">
          <Menu>
            <MenuTrigger asChild>
              <button
                type="button"
                className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left hover:bg-surface-2"
                aria-label="Account menu"
              >
                <Avatar name={me.full_name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium">{me.full_name}</span>
                  <span className="block truncate text-xs text-fg-subtle">
                    {me.roles.join(", ").replace("_", " ")}
                  </span>
                </span>
              </button>
            </MenuTrigger>
            <MenuContent align="start" className="w-56">
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
              <MenuSeparator />
              <MenuItem icon={<LogOut />} onSelect={() => logout.mutate()}>
                Sign out
              </MenuItem>
            </MenuContent>
          </Menu>
        </div>
      </aside>
      <main className="min-w-0 animate-fade-in px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
