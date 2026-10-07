import type { Exam, ExamListItem, ImportJob, MarkSheet, Me } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ImportsPage from "../features/imports/hub";
import ImportJobPage, { outcomeOf } from "../features/imports/job";
import MarkSheetPage from "../features/marks/sheet";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const I = "/api/v1/admin/imports";
const admin: Me = { ...ownerMe, permissions: [...ownerMe.permissions, "imports.manage", "exams.view"] };
const faculty: Me = {
  ...ownerMe,
  roles: ["faculty"],
  permissions: ["exams.view_assigned", "marks.enter_assigned", "imports.marks_assigned"],
};

const listItem = (id: string, name: string, status: ExamListItem["status"]) =>
  ({ id, name, status, term: { session_code: "2025-26" } }) as unknown as ExamListItem;
const examWith = (id: string, papers: [string, string][]) =>
  ({
    id,
    papers: papers.map(([pid, code]) => ({ id: pid, course_code: code, course_name: `Course ${code}` })),
  }) as unknown as Exam;

const job = (extra: Partial<ImportJob> = {}): ImportJob => ({
  id: "j1",
  kind: "marks",
  status: "validated",
  file_name: "ucs301.xlsx",
  created_at: "2026-10-07T10:00:00Z",
  updated_at: "2026-10-07T10:00:05Z",
  created_by_name: "Faculty Person",
  committed_at: null,
  committed_by_name: null,
  params: { exam_id: "e1", paper_id: "p1", scope: "assigned" },
  sheet_name: "Marks",
  sheets: ["Marks"],
  columns: ["Enrollment no.", "Name", "Internal", "External"],
  header_row: 1,
  mapping: { enrollment_no: 0, full_name: 1, "c:INT": 2, "c:EXT": 3 },
  fields: [],
  file_issues: [],
  rows_total: 3,
  rows_valid: 3,
  rows_warning: 0,
  rows_error: 0,
  summary: { create: 2, update: 1, unchanged: 0, shape: "single", papers: ["UCS301"] },
  error_code: null,
  error_detail: null,
  supersedes_id: null,
  resumed: false,
  ...extra,
});

describe("what a marks import will do", () => {
  it("says it in one sentence, per student or per student paper", () => {
    expect(outcomeOf(job())).toBe("Saves marks for 3 students: 2 new, 1 changed.");
    expect(outcomeOf(job({ summary: { create: 0, update: 1, shape: "single", papers: ["UCS301"] } }))).toBe(
      "Saves marks for 1 student: 1 changed.",
    );
    expect(
      outcomeOf(job({ summary: { create: 40, update: 0, shape: "wide", papers: ["UCS301", "UCS302"] } })),
    ).toBe("Saves marks for 40 student papers across UCS301, UCS302: 40 new.");
    expect(outcomeOf(job({ summary: { create: 0, update: 0, unchanged: 3, shape: "single" } }))).toBeNull();
    expect(outcomeOf(job({ kind: "students", summary: { create: 1, update: 2 } }))).toBe(
      "1 new student will be added and 2 existing students will be updated.",
    );
  });
});

describe("imports hub, marks tab", () => {
  it("offers only exams taking marks, builds the template link and uploads for the chosen paper", async () => {
    document.cookie = "sc_csrf=x";
    const uploads: Record<string, string>[] = [];
    mockApi({
      "GET /api/v1/admin/exams": () => ({
        status: 200,
        body: [
          listItem("e0", "Draft exam", "draft"),
          listItem("e1", "Mid-semester", "marks_entry_open"),
          listItem("e2", "Unit test 1", "marks_entry_closed"),
        ],
      }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: examWith("e1", [["p1", "UCS301"]]) }),
      "GET /api/v1/admin/exams/e2": () => ({ status: 200, body: examWith("e2", [["p9", "UMA101"]]) }),
      [`GET ${I}`]: () => ({ status: 200, body: [] }),
      [`POST ${I}`]: (_u, init) => {
        const form = init.body as FormData;
        uploads.push(Object.fromEntries([...form.entries()].filter(([k]) => k !== "file")) as never);
        return { status: 202, body: job({ id: "new1", status: "uploaded" }) };
      },
      [`GET ${I}/new1`]: () => ({ status: 200, body: job({ id: "new1", status: "uploaded" }) }),
    });
    const { container } = renderRoutes(
      [
        { path: "/admin/imports", element: <ImportsPage /> },
        { path: "/admin/imports/:importId", element: <ImportJobPage /> },
      ],
      "/admin/imports?kind=marks",
      (qc) => qc.setQueryData(meKey, admin),
    );
    const examSelect = await screen.findByRole("combobox", { name: "Exam" });
    expect(
      within(examSelect)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Mid-semester · 2025-26", "Unit test 1 · 2025-26 (entry closed)"]);
    const paperSelect = screen.getByRole("combobox", { name: "Papers in the file" });
    await waitFor(() => expect(within(paperSelect).getAllByRole("option")).toHaveLength(2));
    expect(screen.getByRole("link", { name: /template for all papers/i })).toHaveAttribute(
      "href",
      `${I}/template.xlsx?kind=marks&exam_id=e1`,
    );

    const user = userEvent.setup();
    await user.selectOptions(paperSelect, "p1");
    expect(screen.getByRole("link", { name: /template for UCS301/i })).toHaveAttribute(
      "href",
      `${I}/template.xlsx?kind=marks&exam_id=e1&paper_id=p1`,
    );
    // Another exam: its own papers, and the paper choice starts again from "all papers".
    await user.selectOptions(examSelect, "e2");
    await waitFor(() =>
      expect(
        within(paperSelect)
          .getAllByRole("option")
          .map((o) => o.textContent),
      ).toEqual(["All papers", "UMA101 — Course UMA101"]),
    );
    expect(paperSelect).toHaveValue("");
    await user.selectOptions(examSelect, "e1");
    await waitFor(() => expect(within(paperSelect).getAllByRole("option")).toHaveLength(2));
    await user.selectOptions(paperSelect, "p1");

    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    await user.upload(input, new File(["Roll No,INT\nA001,1\n"], "marks.csv", { type: "text/csv" }));
    await screen.findByText(/waiting for a worker/i);
    expect(uploads).toEqual([{ kind: "marks", exam_id: "e1", paper_id: "p1" }]);
  });

  it("explains what to do when no exam is taking marks", async () => {
    mockApi({
      "GET /api/v1/admin/exams": () => ({ status: 200, body: [listItem("e0", "Draft", "draft")] }),
      [`GET ${I}`]: () => ({ status: 200, body: [] }),
    });
    renderRoutes([{ path: "/admin/imports", element: <ImportsPage /> }], "/admin/imports?kind=marks", (qc) =>
      qc.setQueryData(meKey, admin),
    );
    expect(await screen.findByText("No exam is taking marks")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to exams" })).toHaveAttribute("href", "/admin/exams");
  });
});

describe("marks import review", () => {
  const routes = [
    { path: "/admin/imports/:importId", element: <ImportJobPage /> },
    { path: "/marking/imports/:importId", element: <ImportJobPage /> },
  ];

  it("asks before saving, warns about grid changes, and commits", async () => {
    document.cookie = "sc_csrf=x";
    let committed = false;
    mockApi({
      [`GET ${I}/j1`]: () => ({
        status: 200,
        body: committed
          ? job({
              status: "committed",
              committed_at: "2026-10-07T10:01:00Z",
              committed_by_name: "Faculty Person",
              summary: {
                ...job().summary,
                result: { created: 2, updated: 1, unchanged: 0, papers: { UCS301: 3 } },
              },
            })
          : job(),
      }),
      [`GET ${I}/j1/rows`]: () => ({ status: 200, body: { items: [], next_after: null } }),
      [`POST ${I}/j1/commit`]: (_u, init) => {
        expect(JSON.parse(String(init.body))).toEqual({ skip_errors: false });
        committed = true;
        return { status: 202, body: job({ status: "committing" }) };
      },
    });
    renderRoutes(routes, "/marking/imports/j1", (qc) => qc.setQueryData(meKey, faculty));
    expect(await screen.findByText("Saves marks for 3 students: 2 new, 1 changed.")).toBeInTheDocument();
    expect(screen.getByText(/Marks import · UCS301/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Marks entry" })).toHaveAttribute("href", "/marking");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Import 3 rows" }));
    const dialog = await screen.findByRole("dialog", { name: "Save these marks?" });
    expect(within(dialog).getByText("Save these marks?")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(
      /changed one of these marks in the grid since the check, nothing is saved/,
    );
    await user.click(within(dialog).getByRole("button", { name: "Save marks" }));

    expect(await screen.findByText("Marks saved", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("2 new · 1 changed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open marks entry/i })).toHaveAttribute("href", "/marking");
    expect(screen.queryByRole("link", { name: /back to the exam/i })).not.toBeInTheDocument(); // admins only
  });

  it("shows a refused commit with the reason and a way to check again", async () => {
    mockApi({
      [`GET ${I}/j1`]: () => ({
        status: 200,
        body: job({
          error_code: "INVALID_STATE",
          error_detail: "Marks for A001 / UCS301 changed after the file was checked. Check the file again.",
        }),
      }),
      [`GET ${I}/j1/rows`]: () => ({ status: 200, body: { items: [], next_after: null } }),
    });
    renderRoutes(routes, "/admin/imports/j1", (qc) => qc.setQueryData(meKey, admin));
    expect(await screen.findByText("The import didn't go through")).toBeInTheDocument();
    expect(screen.getByText(/changed after the file was checked/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Imports" })).toHaveAttribute(
      "href",
      "/admin/imports?kind=marks",
    );
  });
});

describe("mark sheet import", () => {
  const sheet = {
    exam_id: "e1",
    exam_name: "Finals",
    exam_status: "marks_entry_open",
    marks_deadline: null,
    paper_id: "p1",
    course_code: "UCS301",
    course_name: "Data Structures",
    components: [{ code: "INT", label: "Internal", max: "40.00", min_pass: null }],
    max_total: "40.00",
    pass_total: null,
    cohort_id: "c1",
    cohort_code: "COE-2A",
    cohort_name: "Group A",
    submission_status: "open",
    submitted_at: null,
    submitted_by_name: null,
    return_reason: null,
    can_edit: true,
    can_submit: true,
    can_return: false,
    complete: 0,
    students: [{ student_id: "s1", enrollment_no: "A001", full_name: "Asha Rao", entry: null }],
  } satisfies MarkSheet;
  const url = "/api/v1/exams/e1/papers/p1/cohorts/c1/marks";

  it("offers the cohort's pre-filled template and uploads into the faculty review page", async () => {
    document.cookie = "sc_csrf=x";
    const uploads: Record<string, string>[] = [];
    mockApi({
      [`GET ${url}`]: () => ({ status: 200, body: sheet }),
      [`POST ${I}`]: (_u, init) => {
        const form = init.body as FormData;
        uploads.push(Object.fromEntries([...form.entries()].filter(([k]) => k !== "file")) as never);
        return { status: 202, body: job({ id: "new2", status: "parsing" }) };
      },
      [`GET ${I}/new2`]: () => ({ status: 200, body: job({ id: "new2", status: "parsing" }) }),
    });
    renderRoutes(
      [
        { path: "/marking/:examId/:paperId/:cohortId", element: <MarkSheetPage /> },
        { path: "/marking/imports/:importId", element: <ImportJobPage /> },
      ],
      "/marking/e1/p1/c1",
      (qc) => qc.setQueryData(meKey, faculty),
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Import from Excel" }));
    const dialog = await screen.findByRole("dialog", { name: "Import UCS301 marks for COE-2A" });
    expect(within(dialog).getByRole("link", { name: /download template/i })).toHaveAttribute(
      "href",
      `${I}/template.xlsx?kind=marks&exam_id=e1&paper_id=p1&cohort_id=c1`,
    );
    const input = dialog.querySelector<HTMLInputElement>('input[type="file"]')!;
    await user.upload(input, new File(["x"], "ucs301.xlsx", { type: "application/vnd.ms-excel" }));
    expect(await screen.findByText("Reading your file…")).toBeInTheDocument();
    expect(uploads).toEqual([{ kind: "marks", exam_id: "e1", paper_id: "p1" }]);
  });

  it("isn't offered to someone who can enter marks but not import them", async () => {
    mockApi({ [`GET ${url}`]: () => ({ status: 200, body: sheet }) });
    renderRoutes(
      [{ path: "/marking/:examId/:paperId/:cohortId", element: <MarkSheetPage /> }],
      "/marking/e1/p1/c1",
      (qc) =>
        qc.setQueryData(meKey, { ...faculty, permissions: ["exams.view_assigned", "marks.enter_assigned"] }),
    );
    await screen.findByRole("textbox", { name: "A001 Internal" });
    expect(screen.queryByRole("button", { name: "Import from Excel" })).not.toBeInTheDocument();
  });
});
