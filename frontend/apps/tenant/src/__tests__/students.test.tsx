import type { ImportJob, IssuedCode, Me, Student } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ImportJobPage from "../features/imports/job";
import StudentsPage from "../features/students/list";
import { slipsCsv } from "../features/students/slips";
import { homePathFor, meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const admin: Me = {
  ...ownerMe,
  permissions: [...ownerMe.permissions, "students.manage", "imports.manage", "academics.view"],
};

const student = (n: number, extra: Partial<Student> = {}): Student => ({
  id: `s${n}`,
  enrollment_no: `10230300${n}`,
  full_name: `Student ${n}`,
  date_of_birth: null,
  email: null,
  phone: null,
  guardian_name: null,
  admission_year: 2024,
  status: "active",
  account: "none",
  version: 1,
  created_at: "2026-10-01T10:00:00Z",
  archived_at: null,
  memberships: [
    {
      cohort_id: "c1",
      cohort_code: "CSE-G1",
      cohort_name: "Group 1",
      session_id: "y1",
      session_code: "2025-26",
      session_is_current: true,
      program_id: "p1",
      program_code: "BE",
    },
  ],
  ...extra,
});

const common = {
  "GET /api/v1/admin/students/counts": () => ({
    status: 200,
    body: { active: 2, graduated: 0, withdrawn: 0, archived: 1 },
  }),
  "GET /api/v1/admin/academic-sessions": () => ({ status: 200, body: [] }),
  "GET /api/v1/admin/cohorts": () => ({ status: 200, body: [] }),
};

describe("students list", () => {
  it("lists students with their cohort and account, and searches on the server", async () => {
    const fetchMock = mockApi({
      ...common,
      "GET /api/v1/admin/students": (url) => {
        const q = new URL(url, "http://x").searchParams.get("q");
        const items = q
          ? [student(2, { account: "active" })]
          : [student(1), student(2, { account: "active" })];
        return { status: 200, body: { items, next_cursor: null, total: items.length } };
      },
    });
    renderRoutes([{ path: "/admin/students", element: <StudentsPage /> }], "/admin/students", (qc) =>
      qc.setQueryData(meKey, admin),
    );
    const table = await screen.findByRole("table");
    expect(await within(table).findByRole("link", { name: "Student 1" })).toHaveAttribute(
      "href",
      "/admin/students/s1",
    );
    expect(within(table).getAllByText("CSE-G1")).toHaveLength(2);
    expect(within(table).getByText("No account yet")).toBeInTheDocument();
    expect(within(table).getByText("Activated")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Archived\s*1/ })).toBeInTheDocument();
    expect(screen.getByText("Showing 2 of 2")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("searchbox", { name: "Search students" }), "Student 2");
    await waitFor(() =>
      expect(within(table).queryByRole("link", { name: "Student 1" })).not.toBeInTheDocument(),
    );
    const urls = fetchMock.mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => u.includes("q=Student+2") && u.includes("status=active"))).toBe(true);
  });

  it("guides a new institution to import or add students", async () => {
    mockApi({
      ...common,
      "GET /api/v1/admin/students/counts": () => ({
        status: 200,
        body: { active: 0, graduated: 0, withdrawn: 0, archived: 0 },
      }),
      "GET /api/v1/admin/students": () => ({ status: 200, body: { items: [], next_cursor: null, total: 0 } }),
    });
    renderRoutes([{ path: "/admin/students", element: <StudentsPage /> }], "/admin/students", (qc) =>
      qc.setQueryData(meKey, admin),
    );
    expect(await screen.findByRole("heading", { name: "Add your students" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import a spreadsheet" })).toHaveAttribute(
      "href",
      "/admin/imports",
    );
  });
});

const job = (extra: Partial<ImportJob>): ImportJob => ({
  id: "i1",
  kind: "students",
  status: "validated",
  file_name: "class-list.xlsx",
  created_at: "2026-10-06T10:00:00Z",
  updated_at: "2026-10-06T10:00:05Z",
  created_by_name: "Priya Malhotra",
  committed_at: null,
  committed_by_name: null,
  params: { mode: "upsert" },
  sheet_name: "Students",
  sheets: ["Students"],
  columns: ["Roll No", "Pupil", "Email"],
  header_row: 1,
  mapping: { enrollment_no: 0 },
  fields: [
    { key: "enrollment_no", label: "Enrollment no.", required: true, help: "" },
    { key: "full_name", label: "Full name", required: true, help: "" },
    { key: "email", label: "Email", required: false, help: "" },
  ],
  file_issues: [],
  rows_total: 3,
  rows_valid: 2,
  rows_warning: 0,
  rows_error: 1,
  summary: { create: 2, update: 0, unchanged: 0, skip: 0, cohort_column: false },
  error_code: null,
  error_detail: null,
  supersedes_id: null,
  resumed: false,
  ...extra,
});

describe("import job page", () => {
  it("asks for the missing columns and re-checks with the chosen mapping", async () => {
    document.cookie = "sc_csrf=x";
    const fetchMock = mockApi({
      "GET /api/v1/admin/imports/i1": () => ({
        status: 200,
        body: job({
          status: "needs_mapping",
          file_issues: [
            {
              code: "MISSING_COLUMN",
              severity: "error",
              msg: "No column for “Full name”.",
              field: "full_name",
            },
          ],
        }),
      }),
      "PUT /api/v1/admin/imports/i1/mapping": () => ({ status: 202, body: job({ status: "validating" }) }),
    });
    renderRoutes(
      [{ path: "/admin/imports/:importId", element: <ImportJobPage /> }],
      "/admin/imports/i1",
      (qc) => qc.setQueryData(meKey, admin),
    );
    expect(await screen.findByText("No column for “Full name”.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Column for Full name" }), "1");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Column for Email" }), "1");
    expect(screen.getByRole("alert")).toHaveTextContent("Column B is used for two fields");
    expect(screen.getByRole("button", { name: "Check with this mapping" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Column for Email" }), "2");
    await userEvent.click(screen.getByRole("button", { name: "Check with this mapping" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      mapping: { enrollment_no: 0, full_name: 1, email: 2 },
      header_row: 1,
      sheet_name: "Students",
    });
  });

  it("reviews problems and imports only the valid rows after confirming", async () => {
    document.cookie = "sc_csrf=x";
    const fetchMock = mockApi({
      "GET /api/v1/admin/imports/i1": () => ({ status: 200, body: job({}) }),
      "GET /api/v1/admin/imports/i1/rows": () => ({
        status: 200,
        body: {
          items: [
            {
              row_no: 3,
              raw: ["A2", "Bilal", "nope"],
              normalized: { enrollment_no: "A2", full_name: "Bilal" },
              issues: [
                {
                  code: "INVALID_EMAIL",
                  severity: "error",
                  msg: "“nope” isn't a valid email address.",
                  field: "email",
                },
              ],
              status: "error",
            },
          ],
          next_after: null,
        },
      }),
      "POST /api/v1/admin/imports/i1/commit": () => ({ status: 202, body: job({ status: "committing" }) }),
    });
    renderRoutes(
      [{ path: "/admin/imports/:importId", element: <ImportJobPage /> }],
      "/admin/imports/i1",
      (qc) => qc.setQueryData(meKey, admin),
    );
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("“nope” isn't a valid email address.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Checked rows" })).getByText(/Row 3/)).toBeInTheDocument();
    expect(screen.getByText(/2 new students will be added\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download checked file/ })).toHaveAttribute(
      "href",
      "/api/v1/admin/imports/i1/report.xlsx",
    );
    await userEvent.click(screen.getByRole("button", { name: "Import 2 valid rows" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/1 row with errors will be skipped/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Import" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toEqual({ skip_errors: true });
    });
  });
});

describe("activation slips", () => {
  it("exports CSV that spreadsheets can't execute", () => {
    const codes: IssuedCode[] = [
      {
        student_id: "s1",
        enrollment_no: "A1",
        full_name: '=HYPERLINK("http://evil","x")',
        cohort_code: "CSE-G1",
        code: "ABCDE-12345",
        expires_at: "2027-02-01T00:00:00Z",
      },
    ];
    const csv = slipsCsv(codes);
    expect(csv).toContain(`"'=HYPERLINK(""http://evil"",""x"")"`);
    expect(csv.split("\r\n")[0]).toBe("Enrollment no.,Name,Cohort,Activation code,Valid until,Activate at");
    expect(csv).toContain("ABCDE-12345,2027-02-01,");
  });

  it("sends students to their own home, not the admin area", () => {
    expect(homePathFor({ permissions: ["me.results", "notifications.self"] })).toBe("/me");
    expect(homePathFor({ permissions: ["students.view", "me.results"] })).toBe("/admin");
    expect(homePathFor({ permissions: ["exams.view_assigned"] })).toBe("/marking");
    expect(homePathFor({ permissions: ["notifications.self"] })).toBe("/account");
  });
});
