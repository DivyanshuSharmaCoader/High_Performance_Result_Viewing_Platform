import { formatRelative } from "@scorecode/ui";
import { Bell, CheckCheck } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { useInbox, useMarkRead, useUnread } from "./api";

/**
 * The inbox: a plain disclosure, like the account menu, so the student portal stays light. The list is
 * loaded only when opened; opening an item marks it read and goes to it.
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const unread = useUnread().data?.unread ?? 0;
  const inbox = useInbox(open);
  const markRead = useMarkRead();
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
  const items = inbox.data?.items ?? [];
  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        className="relative grid size-9 place-items-center rounded-full text-fg-muted hover:bg-surface-2 hover:text-fg"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell className="size-5" aria-hidden />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute top-1 right-1 grid h-4 min-w-4 place-items-center rounded-full bg-danger-solid px-1 text-[10px] leading-none font-semibold text-white"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div
          id={id}
          className="absolute right-0 top-full z-40 mt-2 w-[min(22rem,calc(100vw-2rem))] animate-fade-in rounded-xl border border-border bg-surface shadow-lg"
        >
          <div className="flex items-center justify-between gap-2 border-b border-border px-3.5 py-2.5">
            <span className="text-sm font-semibold text-fg">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[12px] font-medium text-brand-ink hover:bg-surface-2"
                onClick={() => markRead.mutate("all")}
              >
                <CheckCheck className="size-3.5" aria-hidden /> Mark all as read
              </button>
            )}
          </div>
          {inbox.isPending ? (
            <p className="px-3.5 py-6 text-center text-[13px] text-fg-subtle">Loading…</p>
          ) : items.length === 0 ? (
            <p className="px-3.5 py-8 text-center text-[13px] text-fg-subtle">
              Nothing yet. You&apos;ll be told here as soon as results are published.
            </p>
          ) : (
            <ul className="max-h-[60vh] overflow-y-auto p-1.5">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none"
                    onClick={() => {
                      if (!n.read) markRead.mutate(n.id);
                      setOpen(false);
                      if (n.link) void navigate(n.link);
                    }}
                  >
                    <span
                      aria-hidden
                      className={`mt-1.5 size-2 shrink-0 rounded-full ${n.read ? "bg-transparent" : "bg-brand"}`}
                    />
                    <span className="min-w-0">
                      <span className={`block text-sm ${n.read ? "text-fg-muted" : "font-semibold text-fg"}`}>
                        {n.title}
                        {!n.read && <span className="sr-only"> (unread)</span>}
                      </span>
                      <span className="block text-[12px] text-fg-subtle">
                        {n.body} · {formatRelative(n.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
