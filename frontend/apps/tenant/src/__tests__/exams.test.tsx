import type { Exam, Me } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ExamWorkspacePage from "../features/exams/workspace";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const admin: Me = {
  ...ownerMe,
  permissions: [...ownerMe.permissions, "exams.view", "exams.manage", "grading.view", "academics.view"],
};

const exam = (extra: Partial<Exam> = {}): Exam => ({
  id: "e1",
  name: "End Semester",
  kind: "semester",
  status: "draft",
  version: 1,
  term: { id: "t1", code: "ODD", name: "Odd semester", session_id: "s1", session_code: "2025-26" },
  grading_scheme_id: "g1",
  grading_scheme_name: "Undergraduate scale",
  grading_scheme_version_id: null,
  marks_deadline: null,
  notes: null,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  cohorts: [{ id: "c1", code: "COE-2A", name: "Group A", program_code: "BE-COE", students: 30 }],
  papers: [],
  checks: [
    { key: "cohorts", ok: true, message: "Add the cohorts sitting this exam." },
    { key: "students", ok: true, message: "Every cohort has students." },
    { key: "papers", ok: false, message: "Add at least one paper with its components." },
    { key: "grading", ok: true, message: "The grading scheme is active." },
  ],
  actions: [{ action: "open_entry", label: "Open marks entry", needs_reason: false }],
  ...extra,
});

const withPaper = (extra: Partial<Exam> = {}) =>
  exam({
    papers: [
      {
        id: "p1",
        course_id: "k1",
        course_code: "UCS301",
        course_name: "Data Structures",
        position: 1,
        components: [
          { code: "MST", label: "Mid-semester", max: "25.00", min_pass: null },
          { code: "EST", label: "End-semester", max: "45.00", min_pass: "18.00" },
        ],
        max_total: "70.00",
        pass_total: null,
        credits: "4.0",
        assignments: [],
        submissions: [],
      },
    ],
    checks: exam().checks.map((c) => ({ ...c, ok: true })),
    ...extra,
  });

const common = {
  "GET /api/v1/admin/grading-schemes": () => ({ status: 200, body: [] }),
  "GET /api/v1/admin/cohorts": () => ({ status: 200, body: [] }),
};

describe("exam workspace", () => {
  it("shows what's missing and won't open marks entry until ready", async () => {
    mockApi({ ...common, "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam() }) });
    renderRoutes(
      [{ path: "/admin/exams/:examId", element: <ExamWorkspacePage /> }],
      "/admin/exams/e1",
      (qc) => qc.setQueryData(meKey, admin),
    );
    const checklist = await screen.findByRole("list", { name: "Readiness" });
    expect(within(checklist).getByText("Add at least one paper with its components.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open marks entry" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete draft" })).toBeInTheDocument();
  });

  it("summarises papers and opens marks entry after confirming", async () => {
    document.cookie = "sc_csrf=x";
    const fetchMock = mockApi({
      ...common,
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: withPaper() }),
      "POST /api/v1/admin/exams/e1/transitions": () => ({
        status: 200,
        body: withPaper({
          status: "marks_entry_open",
          actions: [{ action: "close_entry", label: "Close marks entry", needs_reason: false }],
        }),
      }),
    });
    renderRoutes(
      [{ path: "/admin/exams/:examId", element: <ExamWorkspacePage /> }],
      "/admin/exams/e1",
      (qc) => qc.setQueryData(meKey, admin),
    );
    const papers = await screen.findByRole("list", { name: "Papers" });
    expect(within(papers).getByText(/Mid-semester 25 \+ End-semester 45 \(min 18\)/)).toBeInTheDocument();
    expect(within(papers).getByText("COE-2A: admins only")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open marks entry" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Open marks entry" }),
    );
    await waitFor(() => expect(screen.getByText("Marks entry open")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/transitions"));
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ action: "open_entry", reason: null });
    expect(screen.getByRole("button", { name: "Close marks entry" })).toBeInTheDocument();
  });

  it("asks for a reason before reopening marks entry", async () => {
    mockApi({
      ...common,
      "GET /api/v1/admin/exams/e1": () => ({
        status: 200,
        body: withPaper({
          status: "marks_entry_closed",
          actions: [{ action: "reopen_entry", label: "Reopen marks entry", needs_reason: true }],
        }),
      }),
    });
    renderRoutes(
      [{ path: "/admin/exams/:examId", element: <ExamWorkspacePage /> }],
      "/admin/exams/e1",
      (qc) => qc.setQueryData(meKey, admin),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Reopen marks entry" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Reopen marks entry" })).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "Re-evaluation requested");
    expect(within(dialog).getByRole("button", { name: "Reopen marks entry" })).toBeEnabled();
  });
});
