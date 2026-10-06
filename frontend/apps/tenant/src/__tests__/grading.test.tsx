import type { GradingSchemeDetail, Me } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { toConfig, toDraft } from "../features/grading/api";
import GradingEditorPage from "../features/grading/editor";
import GradingPage from "../features/grading/list";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const admin: Me = { ...ownerMe, permissions: [...ownerMe.permissions, "grading.view", "grading.manage"] };

const bandsConfig = {
  strategy: "percentage_bands",
  bands: [
    { grade: "A", min_percentage: "80", grade_point: null, label: null },
    { grade: "B", min_percentage: "60", grade_point: null, label: null },
    { grade: "F", min_percentage: "0", grade_point: null, label: null },
  ],
  fail_grade: "F",
  absent_grade: "AB",
  pass_rules: { paper_pass_percentage: "40", overall_pass_percentage: null, require_all_papers: true },
  rounding: { mode: "half_up", total_places: 2, percentage_places: 2, gpa_places: 2 },
};

const scheme = (extra: Partial<GradingSchemeDetail> = {}): GradingSchemeDetail => ({
  id: "g1",
  name: "School bands",
  strategy: "percentage_bands",
  strategy_label: "Percentage bands",
  description: null,
  is_default: true,
  archived_at: null,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  version: 1,
  version_id: "v1",
  config: bandsConfig,
  versions: [
    {
      id: "v1",
      version: 1,
      note: null,
      created_at: "2026-10-01T10:00:00Z",
      created_by_name: "Priya Malhotra",
    },
  ],
  saved: null,
  ...extra,
});

const preview = {
  outcome: "pass",
  total: "188.00",
  max_total: "300",
  percentage: "62.67",
  grade: "B",
  grade_point: null,
  sgpa: null,
  credits_attempted: null,
  credits_earned: null,
  papers: [],
};

describe("grading config round trip", () => {
  it("keeps every field the API stores", () => {
    expect(toConfig(toDraft(bandsConfig))).toEqual(bandsConfig);
    const credit = {
      strategy: "credit_gpa",
      bands: [{ grade: "O", min_percentage: "90.000", grade_point: "10.00", label: null }],
      fail_grade: "F",
      absent_grade: "AB",
      count_absent_as_attempted: false,
      pass_rules: { paper_pass_percentage: "40", overall_pass_percentage: null, require_all_papers: true },
      rounding: { mode: "half_even", total_places: 2, percentage_places: 1, gpa_places: 2 },
    };
    const draft = toDraft(credit);
    expect(draft.bands[0]).toEqual({ grade: "O", min_percentage: "90", grade_point: "10", label: "" });
    expect(toConfig(draft)).toMatchObject({
      count_absent_as_attempted: false,
      rounding: { mode: "half_even" },
    });
    expect(toConfig(toDraft({ strategy: "marks_only", ranking: "dense" }))).toMatchObject({
      strategy: "marks_only",
      ranking: "dense",
    });
  });
});

describe("grading screens", () => {
  it("lists schemes with the default marked", async () => {
    mockApi({
      "GET /api/v1/admin/grading-schemes": () => ({
        status: 200,
        body: [scheme(), scheme({ id: "g2", name: "Test series", is_default: false, version: 3 })],
      }),
    });
    renderRoutes([{ path: "/admin/grading", element: <GradingPage /> }], "/admin/grading", (qc) =>
      qc.setQueryData(meKey, admin),
    );
    const list = await screen.findByRole("list", { name: "Grading schemes" });
    const items = within(list).getAllByRole("listitem");
    expect(within(items[0]!).getByText("Default")).toBeInTheDocument();
    expect(within(items[1]!).queryByText("Default")).not.toBeInTheDocument();
    expect(within(items[1]!).getByText(/Version 3/)).toBeInTheDocument();
    expect(within(items[0]!).getByRole("link", { name: "School bands" })).toHaveAttribute(
      "href",
      "/admin/grading/g1",
    );
  });

  it("edits bands, previews live and saves a new version based on the loaded one", async () => {
    document.cookie = "sc_csrf=x";
    const previews: unknown[] = [];
    const fetchMock = mockApi({
      "GET /api/v1/admin/grading-schemes/g1": () => ({ status: 200, body: scheme() }),
      "POST /api/v1/admin/grading-schemes/preview": (_u, init) => {
        previews.push(JSON.parse(String(init.body)));
        return { status: 200, body: preview };
      },
      "POST /api/v1/admin/grading-schemes/g1/versions": () => ({
        status: 200,
        body: scheme({ version: 2, saved: true }),
      }),
    });
    renderRoutes(
      [{ path: "/admin/grading/:schemeId", element: <GradingEditorPage /> }],
      "/admin/grading/g1",
      (qc) => qc.setQueryData(meKey, admin),
    );
    const bandB = await screen.findByRole("textbox", { name: "Band 2 lowest percentage" });
    expect(bandB).toHaveValue("60");
    expect(screen.getByRole("textbox", { name: "Band 3 lowest percentage" })).toBeDisabled(); // last band: 0%
    expect(await screen.findByText("62.67%")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Save/ })).not.toBeInTheDocument(); // nothing to save yet

    await userEvent.clear(bandB);
    await userEvent.type(bandB, "65");
    await waitFor(() =>
      expect(
        previews.some((p) => (p as { config: typeof bandsConfig }).config.bands[1]?.min_percentage === "65"),
      ).toBe(true),
    );
    await userEvent.type(screen.getByRole("textbox", { name: "What changed? (optional)" }), "Stricter B");
    await userEvent.click(screen.getByRole("button", { name: "Save as version 2" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/versions"));
      expect(post).toBeDefined();
      const body = JSON.parse(String(post?.[1]?.body));
      expect(body.based_on).toBe(1);
      expect(body.note).toBe("Stricter B");
      expect(body.config.bands[1].min_percentage).toBe("65");
    });
  });

  it("is read-only for people who can only view", async () => {
    mockApi({
      "GET /api/v1/admin/grading-schemes/g1": () => ({ status: 200, body: scheme() }),
      "POST /api/v1/admin/grading-schemes/preview": () => ({ status: 200, body: preview }),
    });
    const viewer: Me = { ...ownerMe, permissions: [...ownerMe.permissions, "grading.view"] };
    renderRoutes(
      [{ path: "/admin/grading/:schemeId", element: <GradingEditorPage /> }],
      "/admin/grading/g1",
      (qc) => qc.setQueryData(meKey, viewer),
    );
    expect(await screen.findByRole("textbox", { name: "Band 1 grade" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Save/ })).not.toBeInTheDocument();
  });
});
