import { Avatar, TenantMark } from "@scorecode/ui";
import { House, LogOut, UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
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
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur print:static print:border-0">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between gap-3 px-4">
          <Link to="/me" className="flex min-w-0 items-center gap-2.5">
            <TenantMark
              name={b.display_name}
              logoUrl={b.logo_url ? `${b.logo_url}?v=${b.logo_version}` : null}
              size={28}
            />
            <span className="truncate text-sm font-semibold text-fg">{b.short_name ?? b.display_name}</span>
          </Link>
          <AccountMenu
            name={me.full_name}
            loginId={me.login_id}
            onHome={() => void navigate("/me")}
            onAccount={() => void navigate("/me/account")}
            onSignOut={() => logout.mutate()}
          />
        </div>
      </header>
      <main id="main" className="mx-auto max-w-3xl px-4 py-6 sm:py-8">
        {children}
      </main>
      {b.show_powered_by && (
        <footer className="pb-8 text-center text-xs text-fg-subtle print:hidden">Powered by ScoreCode</footer>
      )}
    </div>
  );
}

/**
 * The student account menu: a plain disclosure (button + panel) rather than the staff menu component, so
 * the student portal doesn't download a positioning engine for three links. Escape and outside clicks
 * close it; focus returns to the button.
 */
function AccountMenu({
  name,
  loginId,
  onHome,
  onAccount,
  onSignOut,
}: {
  name: string;
  loginId: string;
  onHome: () => void;
  onAccount: () => void;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const item =
    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-fg hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none [&_svg]:size-4 [&_svg]:text-fg-subtle";
  const pick = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };
  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        className="rounded-full p-0.5 hover:bg-surface-2"
        aria-label="Account menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        <Avatar name={name} size="sm" />
      </button>
      {open && (
        <div
          id={id}
          className="absolute right-0 top-full z-40 mt-2 w-56 animate-fade-in rounded-xl border border-border bg-surface p-1.5 shadow-lg"
        >
          <div className="px-2.5 py-2 text-[13px]">
            <span className="block truncate font-medium text-fg">{name}</span>
            <span className="block truncate font-mono text-fg-subtle">{loginId}</span>
          </div>
          <div className="my-1 h-px bg-border" />
          <button type="button" className={item} onClick={pick(onHome)}>
            <House aria-hidden /> Home
          </button>
          <button type="button" className={item} onClick={pick(onAccount)}>
            <UserRound aria-hidden /> Password & sessions
          </button>
          <div className="my-1 h-px bg-border" />
          <button type="button" className={item} onClick={pick(onSignOut)}>
            <LogOut aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
