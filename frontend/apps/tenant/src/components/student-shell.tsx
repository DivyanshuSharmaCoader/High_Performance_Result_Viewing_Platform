import {
  Avatar,
  Menu,
  MenuContent,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
  TenantMark,
} from "@scorecode/ui";
import { House, LogOut, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { useLogout, useSession } from "../lib/session";
import { useTenant } from "../lib/tenant";

/** The student portal frame: light (students download as little as possible — docs/09 §7). */
export function StudentShell({ children }: { children: ReactNode }) {
  const tenant = useTenant();
  const me = useSession();
  const logout = useLogout();
  const navigate = useNavigate();
  const b = tenant.branding;
  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between gap-3 px-4">
          <Link to="/me" className="flex min-w-0 items-center gap-2.5">
            <TenantMark
              name={b.display_name}
              logoUrl={b.logo_url ? `${b.logo_url}?v=${b.logo_version}` : null}
              size={28}
            />
            <span className="truncate text-sm font-semibold text-fg">{b.short_name ?? b.display_name}</span>
          </Link>
          <Menu>
            <MenuTrigger asChild>
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-surface-2"
                aria-label="Account menu"
              >
                <Avatar name={me.full_name} size="sm" />
              </button>
            </MenuTrigger>
            <MenuContent align="end" className="w-56">
              <MenuLabel>
                <span className="block truncate text-fg">{me.full_name}</span>
                <span className="block truncate font-mono font-normal">{me.login_id}</span>
              </MenuLabel>
              <MenuSeparator />
              <MenuItem icon={<House />} onSelect={() => void navigate("/me")}>
                Home
              </MenuItem>
              <MenuItem icon={<UserRound />} onSelect={() => void navigate("/me/account")}>
                Password & sessions
              </MenuItem>
              <MenuSeparator />
              <MenuItem icon={<LogOut />} onSelect={() => logout.mutate()}>
                Sign out
              </MenuItem>
            </MenuContent>
          </Menu>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-3xl px-4 py-6 sm:py-8">
        {children}
      </main>
      {b.show_powered_by && (
        <footer className="pb-8 text-center text-xs text-fg-subtle">Powered by ScoreCode</footer>
      )}
    </div>
  );
}
