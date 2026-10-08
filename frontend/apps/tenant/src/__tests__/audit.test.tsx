import type { AuditEntry } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AuditLogPage from "../features/admin/audit";
import { describeAction } from "../features/admin/audit-format";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const entry = (extra: Partial<AuditEntry> = {}): AuditEntry => ({
  id: "a1",
  occurred_at: "2026-10-08T06:00:00Z",
  actor_type: "user",
  actor_id: "u1",
  actor_label: "Priya Malhotra",
  action: "results.approved",
  entity_type: "exam",
  entity_id: "e1",
  summary: null,
  before: { status: "processed" },
  after: { status: "approved" },
  reason: null,
  ip: "203.0.113.7",
  ...extra,
});

const render = (path = "/admin/audit-log") =>
  renderRoutes([{ path: "/admin/audit-log", element: <AuditLogPage /> }], path, (qc) =>
    qc.setQueryData(meKey, { ...ownerMe, permissions: [...ownerMe.permissions, "staff.view"] }),
  );

describe("audit log", () => {
  it("filters by kind of activity, person and dates, and shows what changed", async () => {
    const seen: URLSearchParams[] = [];
    mockApi({
      "GET /api/v1/admin/audit-logs": (url) => {
        seen.push(new URL(url, "http://x").searchParams);
        return { status: 200, body: { items: [entry()], next_cursor: null } };
      },
      "GET /api/v1/admin/staff": () => ({
        status: 200,
        body: [
          {
            id: "u1",
            full_name: "Priya Malhotra",
            email: "p@x.org",
            role: "institution_admin",
            status: "active",
            last_login_at: null,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    });
    render();
    expect(await screen.findByText("Results approved")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Filter activity"), "results.");
    await user.selectOptions(await screen.findByLabelText("Filter by person"), "u1");
    await user.type(screen.getByLabelText("From"), "2026-10-01");
    await user.type(screen.getByLabelText("To"), "2026-10-08");
    await waitFor(() => {
      const last = seen.at(-1)!;
      expect(last.get("action")).toBe("results.");
      expect(last.get("actor_id")).toBe("u1");
      expect(last.get("since")).toBe(new Date("2026-10-01T00:00:00").toISOString());
      expect(last.get("until")).toBe(new Date("2026-10-09T00:00:00").toISOString()); // the whole last day
    });

    await user.click(screen.getByRole("button", { name: "Show details" }));
    const diff = screen.getByRole("table", { name: "What changed" });
    expect(within(diff).getByText("processed")).toBeInTheDocument();
    expect(within(diff).getByText("approved")).toBeInTheDocument();
    expect(screen.getByText(/IP 203.0.113.7/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect([...seen.at(-1)!.keys()].sort()).toEqual(["limit"]));
  });

  it("opens one record's history from a link, and can widen back out", async () => {
    const seen: URLSearchParams[] = [];
    mockApi({
      "GET /api/v1/admin/audit-logs": (url) => {
        seen.push(new URL(url, "http://x").searchParams);
        return { status: 200, body: { items: [], next_cursor: null } };
      },
      "GET /api/v1/admin/staff": () => ({ status: 200, body: [] }),
    });
    render("/admin/audit-log?entity_id=e1&label=Finals");
    expect(await screen.findByText("History of Finals")).toBeInTheDocument();
    expect(await screen.findByText("Nothing matches these filters")).toBeInTheDocument();
    expect(seen[0]!.get("entity_id")).toBe("e1");
    await userEvent.setup().click(screen.getByRole("button", { name: "Show all records" }));
    await waitFor(() => expect(seen.at(-1)!.get("entity_id")).toBeNull());
  });

  it("describes every kind of action in plain words", () => {
    expect(describeAction("exam.open_entry")).toBe("Marks entry opened");
    expect(describeAction("session.created")).toBe("Academic session created");
    expect(describeAction("cohort.archived")).toBe("Section archived");
    expect(describeAction("grading_scheme.updated")).toBe("Grading scheme changed");
    expect(describeAction("verification.revoked")).toBe("Marksheet verification revoked");
    expect(describeAction("something.new_thing")).toBe("Something new thing");
  });
});
