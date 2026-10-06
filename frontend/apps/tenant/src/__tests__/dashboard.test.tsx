import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "../features/admin/dashboard";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const onboarding = {
  completed: 1,
  total: 3,
  dismissed: false,
  steps: [
    {
      key: "profile",
      title: "Complete your institution profile",
      description: "d",
      href: "/admin/settings",
      required_for_publishing: true,
      done: false,
      detail: "Add your address",
    },
    {
      key: "logo",
      title: "Upload your logo",
      description: "Shown on the portal",
      href: "/admin/settings/branding",
      required_for_publishing: false,
      done: true,
      detail: null,
    },
    {
      key: "staff",
      title: "Invite your team",
      description: "Add administrators",
      href: "/admin/staff",
      required_for_publishing: false,
      done: false,
      detail: "1 staff account",
    },
  ],
};

describe("admin dashboard onboarding checklist", () => {
  it("shows progress, the next step and which steps block publishing; hiding calls the API", async () => {
    document.cookie = "sc_csrf=x";
    const fetchMock = mockApi({
      "GET /api/v1/admin/onboarding": () => ({ status: 200, body: onboarding }),
      "PUT /api/v1/admin/onboarding": () => ({ status: 200, body: { ...onboarding, dismissed: true } }),
      "GET /api/v1/admin/subscription": () => ({
        status: 200,
        body: {
          plan_code: "free",
          plan_name: "Free",
          status: "active",
          period_end: null,
          features: {},
          overrides: [],
          limits: [{ key: "max_students", description: "x", limit: 150, used: 20 }],
        },
      }),
      "GET /api/v1/admin/audit-logs": () => ({ status: 200, body: { items: [], next_cursor: null } }),
      "GET /api/v1/me": () => ({ status: 200, body: ownerMe }),
    });
    const { container } = renderRoutes([{ path: "/admin", element: <DashboardPage /> }], "/admin", (qc) =>
      qc.setQueryData(meKey, ownerMe),
    );
    const section = await screen.findByRole("region", { name: "Set up your institution" });
    expect(within(section).getByText(/1 of 3 steps done/)).toBeInTheDocument();
    expect(within(section).getByText(/Next: complete your institution profile/)).toBeInTheDocument();
    expect(within(section).getByText("Needed to publish")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: /Upload your logo/ })).toHaveAttribute(
      "href",
      "/admin/settings/branding",
    );
    expect(screen.getByRole("meter", { name: "Active students" })).toHaveAttribute("aria-valuenow", "20");
    await userEvent.click(within(section).getByRole("button", { name: "Hide setup guide" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true);
    expect(container).toBeTruthy();
  });
});
