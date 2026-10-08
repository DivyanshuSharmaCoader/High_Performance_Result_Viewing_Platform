import type { AppNotification, Me } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StudentShell } from "../components/student-shell";
import AccountPage from "../features/account/account";
import { meKey } from "../lib/session";
import { TenantProvider, tenantConfigKey } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const student: Me = {
  ...ownerMe,
  full_name: "Aarav Gupta",
  login_id: "102401001",
  email: null,
  kind: "student",
  roles: ["student"],
  permissions: ["me.results"],
};

const note = (id: string, title: string, read = false): AppNotification => ({
  id,
  kind: "result_published",
  title,
  body: "Your result and marksheet are ready.",
  link: `/me/results/${id}`,
  created_at: "2026-10-08T06:00:00Z",
  read,
});

const render = (path = "/me") =>
  renderRoutes(
    [
      {
        path: "/me",
        element: (
          <TenantProvider>
            <StudentShell>
              <p>Home</p>
            </StudentShell>
          </TenantProvider>
        ),
      },
      { path: "/me/results/:id", element: <p>Result page</p> },
      {
        path: "/me/account",
        element: (
          <TenantProvider>
            <AccountPage />
          </TenantProvider>
        ),
      },
    ],
    path,
    (qc) => {
      qc.setQueryData(meKey, student);
      qc.setQueryData(tenantConfigKey, tenantConfig);
    },
  );

describe("notifications", () => {
  it("shows the unread count, opens the inbox, and an item marks itself read and opens", async () => {
    document.cookie = "sc_csrf=x";
    const read: string[] = [];
    mockApi({
      "GET /api/v1/me/notifications/unread-count": () => ({
        status: 200,
        body: { unread: read.length ? 1 : 2 },
      }),
      "GET /api/v1/me/notifications": () => ({
        status: 200,
        body: {
          items: [note("p2", "Finals results are available"), note("p1", "Mid-term results are available")],
          unread: 2,
          next_before: null,
        },
      }),
      "POST /api/v1/me/notifications/p2/read": (url) => {
        read.push(url);
        return { status: 200, body: { ok: true } };
      },
    });
    render();
    const bell = await screen.findByRole("button", { name: "Notifications, 2 unread" });
    const user = userEvent.setup();
    await user.click(bell);
    expect(bell).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(bell.getAttribute("aria-controls")!)!;
    const item = await within(panel).findByRole("button", { name: /Finals results are available/ });
    expect(within(item).getByText("(unread)")).toHaveClass("sr-only");
    await user.click(item);
    expect(await screen.findByText("Result page")).toBeInTheDocument();
    await waitFor(() => expect(read).toHaveLength(1));
  });

  it("marks everything read at once, and says when there's nothing", async () => {
    document.cookie = "sc_csrf=x";
    let cleared = false;
    mockApi({
      "GET /api/v1/me/notifications/unread-count": () => ({ status: 200, body: { unread: cleared ? 0 : 1 } }),
      "GET /api/v1/me/notifications": () => ({
        status: 200,
        body: {
          items: cleared ? [] : [note("p2", "Finals results are available")],
          unread: 0,
          next_before: null,
        },
      }),
      "POST /api/v1/me/notifications/read-all": () => {
        cleared = true;
        return { status: 200, body: { updated: 1 } };
      },
    });
    render();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));
    await user.click(await screen.findByRole("button", { name: "Mark all as read" }));
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeInTheDocument();
    expect(await screen.findByText(/as soon as results are published/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Notifications" })).toHaveAttribute("aria-expanded", "false");
  });

  it("lets a student turn result emails off", async () => {
    document.cookie = "sc_csrf=x";
    const saved: unknown[] = [];
    mockApi({
      "GET /api/v1/me/sessions": () => ({ status: 200, body: [] }),
      "GET /api/v1/me/preferences": () => ({ status: 200, body: { email_results: true } }),
      "PUT /api/v1/me/preferences": (_u, init) => {
        const body = JSON.parse(String(init.body));
        saved.push(body);
        return { status: 200, body };
      },
    });
    render("/me/account");
    const toggle = await screen.findByRole("switch", { name: /Email me when new results are published/ });
    expect(toggle).toBeChecked();
    await userEvent.setup().click(toggle);
    await waitFor(() => expect(saved).toEqual([{ email_results: false }]));
    await waitFor(() => expect(toggle).not.toBeChecked());
  });
});
