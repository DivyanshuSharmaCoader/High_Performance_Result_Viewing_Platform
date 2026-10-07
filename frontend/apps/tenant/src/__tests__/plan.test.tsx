import { ApiError, type Me, type PlanCatalogue, type SubscriptionOut } from "@scorecode/api-client";
import { toast } from "@scorecode/ui";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import PlanPage from "../features/admin/plan";
import { TrialBanner } from "../features/plan/trial-banner";
import { toastError } from "../lib/forms";
import { meKey } from "../lib/session";
import { TenantProvider, tenantConfigKey } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

const owner: Me = { ...ownerMe, permissions: [...ownerMe.permissions, "subscription.manage"] };
const admin: Me = { ...ownerMe, roles: ["institution_admin"] };

const limit = (key: string, lim: number | null, used: number) => ({
  key,
  description: key,
  limit: lim,
  used,
});

const sub = (
  extra: Partial<SubscriptionOut> = {},
  trial: Partial<SubscriptionOut["trial"]> = {},
): SubscriptionOut => ({
  plan_code: "free",
  plan_name: "Free",
  status: "active",
  period_end: null,
  limits: [
    limit("max_students", 150, 42),
    limit("max_staff", 5, 2),
    limit("max_admins", 2, 1),
    limit("max_storage_mb", 1024, 3),
    limit("max_published_exams_per_year", 6, 1),
    limit("history_years", 1, 0),
    limit("max_import_rows", 5000, 0),
  ],
  features: { custom_branding: false, scheduled_publication: false, credit_grading: true },
  overrides: [],
  trial: {
    state: "available",
    days: 30,
    plan_name: "Pro trial",
    started_at: null,
    ends_at: null,
    days_left: null,
    can_start: true,
    ...trial,
  },
  ...extra,
});

const plan = (code: string, name: string, price: number | null, students: number | null, extra = {}) => ({
  code,
  name,
  description: "",
  price_paise_yearly: price,
  limits: {
    max_students: students,
    max_staff: 5,
    max_admins: 2,
    max_published_exams_per_year: 6,
    history_years: 1,
    max_storage_mb: 1024,
  },
  features: { custom_branding: false, ...extra },
});

const CATALOGUE: PlanCatalogue = {
  plans: [
    plan("free", "Free", 0, 150),
    plan("starter", "Starter", 799_900, 600, { custom_branding: true }),
    plan("growth", "Growth", 1_999_900, 2000, { custom_branding: true, scheduled_publication: true }),
    plan("pro", "Pro", 4_499_900, 5000, { custom_branding: true, custom_domain: true }),
  ],
  trial: plan("trial", "Pro trial", null, 1000),
  trial_days: 30,
};

const render = (me: Me, path = "/admin/plan") =>
  renderRoutes(
    [
      {
        path: "/admin/plan",
        element: (
          <TenantProvider>
            <PlanPage />
          </TenantProvider>
        ),
      },
      { path: "/admin", element: <TrialBanner /> },
    ],
    path,
    (qc) => {
      qc.setQueryData(meKey, me);
      qc.setQueryData(tenantConfigKey, tenantConfig);
    },
  );

describe("plan page", () => {
  it("lets the owner start the trial after confirming, and shows the countdown", async () => {
    document.cookie = "sc_csrf=x";
    let started = false;
    const ends = new Date(Date.now() + 30 * 86_400_000).toISOString();
    mockApi({
      "GET /api/v1/admin/subscription": () => ({ status: 200, body: sub() }),
      "GET /api/v1/plans": () => ({ status: 200, body: CATALOGUE }),
      "GET /api/v1/me": () => ({ status: 200, body: owner }),
      "GET /api/v1/tenant/config": () => ({ status: 200, body: tenantConfig }),
      "POST /api/v1/admin/subscription/trial": () => {
        started = true;
        return {
          status: 200,
          body: sub(
            { plan_code: "trial", plan_name: "Pro trial", status: "trialing", period_end: ends },
            {
              state: "active",
              started_at: new Date().toISOString(),
              ends_at: ends,
              days_left: 30,
              can_start: false,
            },
          ),
        };
      },
    });
    const success = vi.spyOn(toast, "success");
    render(owner);
    expect(
      await screen.findByRole("heading", { name: "Try everything in Pro, free for 30 days" }),
    ).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Start my free trial" }));
    const dialog = await screen.findByRole("dialog", { name: "Start your 30-day Pro trial?" });
    expect(dialog).toHaveTextContent(/nothing is charged and nothing is deleted/);
    await user.click(within(dialog).getByRole("button", { name: "Start trial" }));
    expect(await screen.findByText("30 days left in your Pro trial")).toBeInTheDocument();
    expect(started).toBe(true);
    expect(success).toHaveBeenCalledWith("Your Pro trial has started", expect.anything());
    expect(screen.getByRole("link", { name: "Keep Pro" }).getAttribute("href")).toMatch(
      /^mailto:sales@scorecode\.in/,
    );
  });

  it("explains a refusal in place, with a way to reach a person", async () => {
    document.cookie = "sc_csrf=x";
    mockApi({
      "GET /api/v1/admin/subscription": () => ({ status: 200, body: sub() }),
      "GET /api/v1/plans": () => ({ status: 200, body: CATALOGUE }),
      "POST /api/v1/admin/subscription/trial": () => ({
        status: 409,
        body: {
          code: "trial-unavailable",
          title: "Trial not available",
          detail:
            "We couldn't start the trial automatically. Write to support@scorecode.in and we'll start it.",
          reason: "review",
        },
      }),
    });
    render(owner);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start my free trial" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Start trial" }));
    expect(await screen.findByText("Almost there")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Write to support" }).getAttribute("href")).toMatch(
      /^mailto:support@/,
    );
  });

  it("tells administrators who can start it", async () => {
    mockApi({
      "GET /api/v1/admin/subscription": () => ({ status: 200, body: sub({}, { can_start: false }) }),
      "GET /api/v1/plans": () => ({ status: 200, body: CATALOGUE }),
    });
    render(admin);
    expect(await screen.findByText(/owner can start the trial/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start my free trial" })).not.toBeInTheDocument();
  });

  it("compares plans with the current one marked, and flags a full limit", async () => {
    const full = sub();
    full.limits[0] = limit("max_students", 150, 150);
    mockApi({
      "GET /api/v1/admin/subscription": () => ({ status: 200, body: full }),
      "GET /api/v1/plans": () => ({ status: 200, body: CATALOGUE }),
    });
    render(owner);
    const table = await screen.findByRole("table", { name: "Plans and what they include" });
    const header = within(table).getByRole("columnheader", { name: /Free/ });
    expect(header).toHaveTextContent("Current");
    expect(within(table).getByRole("columnheader", { name: /Growth/ })).toHaveTextContent("₹19,999 / year");
    expect(within(table).getByRole("row", { name: /Active students/ })).toHaveTextContent("1506002,0005,000");
    expect(screen.getByText(/reached the limit for active students/)).toHaveTextContent(
      "or start the free trial",
    );
  });
});

describe("trial banner", () => {
  it("counts down on every staff page, turns amber in the last week, and can be hidden", async () => {
    const ends = new Date(Date.now() + 5 * 86_400_000).toISOString();
    mockApi({
      "GET /api/v1/admin/subscription": () => ({
        status: 200,
        body: sub({ status: "trialing" }, { state: "active", ends_at: ends, days_left: 5, can_start: false }),
      }),
    });
    render({ ...owner, permissions: [...owner.permissions, "subscription.view"] }, "/admin");
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("Pro trial: 5 days left.");
    expect(banner).toHaveTextContent("back on Free — nothing is deleted");
    const user = userEvent.setup();
    await user.click(within(banner).getByRole("button", { name: "Hide for now" }));
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });
});

describe("plan limit errors", () => {
  it("offer the way to the plan page", () => {
    const error = vi.spyOn(toast, "error");
    toastError(
      new ApiError(402, {
        code: "limit-exceeded",
        title: "Plan limit reached",
        detail: "Your plan includes 150 active students.",
      }),
    );
    expect(error).toHaveBeenCalledWith(
      "Plan limit reached",
      expect.objectContaining({ action: expect.objectContaining({ label: "See plans" }) }),
    );
    toastError(new ApiError(409, { code: "conflict", title: "Conflict", detail: "Changed meanwhile." }));
    expect(error.mock.calls[1]![1]).toMatchObject({ action: undefined });
  });
});
