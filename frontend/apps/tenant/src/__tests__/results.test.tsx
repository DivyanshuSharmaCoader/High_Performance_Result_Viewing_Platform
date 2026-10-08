import type { Exam, Me, ResultStudent, ResultsOverview } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReauthProvider } from "../components/reauth";
import ExamResultsPage from "../features/results/page";
import { meKey } from "../lib/session";
import { TenantProvider, tenantConfigKey } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

vi.mock("../lib/navigate", () => ({ goTo: vi.fn() }));
import { goTo } from "../lib/navigate";

afterEach(() => vi.restoreAllMocks());

const URL = "/api/v1/admin/exams/e1/results";
const admin: Me = {
  ...ownerMe,
  permissions: [...ownerMe.permissions, "exams.view", "results.view", "results.process", "results.approve"],
};

const actions = (extra: Partial<ResultsOverview["actions"]> = {}): ResultsOverview["actions"] => ({
  can_process: false,
  can_discard: false,
  can_approve: false,
  can_reject: false,
  can_revoke: false,
  approve_blocked_reason: null,
  ...extra,
});

const STATS = {
  students: 4,
  outcomes: { pass: 2, fail: 1, absent: 1, withheld: 0, incomplete: 0 },
  pass_percentage: "66.7",
  average_percentage: "53.33",
  median_percentage: "50",
  histogram: Array.from({ length: 10 }, (_, i) => ({
    from: i * 10,
    to: i * 10 + 10,
    count: [0, 0, 1, 0, 0, 1, 0, 0, 1, 0][i]!,
  })),
  grades: [
    { grade: "A+", count: 1 },
    { grade: "B", count: 1 },
    { grade: "F", count: 1 },
  ],
  papers: [
    {
      paper_id: "p1",
      course_code: "UCS301",
      course_name: "Data Structures",
      max_total: "100",
      appeared: 3,
      passed: 2,
      pass_percentage: "66.7",
      absent: 1,
      incomplete: 0,
      average: "53.33",
      highest: "85",
      lowest: "25",
    },
  ],
};

const run = (
  extra: Partial<NonNullable<ResultsOverview["run"]>> = {},
): NonNullable<ResultsOverview["run"]> => ({
  id: "r1",
  revision: 1,
  status: "completed",
  created_at: "2026-10-07T10:00:00Z",
  finished_at: "2026-10-07T10:00:03Z",
  started_by_name: "Priya Malhotra",
  error_detail: null,
  students: 4,
  input_hash: "a".repeat(64),
  content_hash: "b".repeat(64),
  scheme: { name: "Scale", version: 2 },
  override_reason: null,
  stats: STATS,
  anomalies: [
    {
      code: "ALL_MAX",
      severity: "warning",
      title: "Full marks in every paper",
      count: 1,
      items: [
        {
          student_id: "s1",
          enrollment_no: "A001",
          full_name: "Asha Rao",
          detail: "Full marks in every paper.",
        },
      ],
    },
  ],
  ...extra,
});

const overview = (extra: Partial<ResultsOverview> = {}): ResultsOverview => ({
  exam_id: "e1",
  exam_name: "Finals",
  exam_status: "processed",
  approval_mode: "single",
  run: run(),
  runs: [
    {
      id: "r1",
      revision: 1,
      status: "completed",
      created_at: "2026-10-07T10:00:00Z",
      started_by_name: "Priya Malhotra",
    },
  ],
  approvals: [],
  unsubmitted: [],
  actions: actions({ can_process: true, can_discard: true, can_approve: true, can_reject: true }),
  ...extra,
});

const student: ResultStudent = {
  student_id: "s1",
  enrollment_no: "A001",
  full_name: "Asha Rao",
  cohort_code: "COE-2A",
  outcome: "pass",
  total: "85.000",
  max_total: "100.000",
  percentage: "85.000",
  grade: null,
  grade_point: null,
  sgpa: "9.000",
  credits_attempted: "4.00",
  credits_earned: "4.00",
  rank: null,
  notes: [],
  papers: [
    {
      exam_paper_id: "p1",
      outcome: "pass",
      attendance: "present",
      components: { INT: "35", EXT: "50" },
      total: "85.000",
      max_total: "100.000",
      percentage: "85.000",
      grade: "A+",
      grade_point: "9.000",
      credits: "4.00",
      failed_components: [],
      missing_components: [],
    },
  ],
};

const exam = {
  id: "e1",
  kind: "semester",
  term: { name: "Odd semester", session_code: "2025-26" },
  papers: [
    {
      id: "p1",
      course_code: "UCS301",
      course_name: "Data Structures",
      credits: "4.0",
      components: [
        { code: "INT", label: "Internal", max: "40" },
        { code: "EXT", label: "External", max: "60" },
      ],
    },
  ],
} as unknown as Exam;

const render = (me: Me = admin) =>
  renderRoutes(
    [
      {
        path: "/admin/exams/:examId/results",
        element: (
          <TenantProvider>
            <ReauthProvider>
              <ExamResultsPage />
            </ReauthProvider>
          </TenantProvider>
        ),
      },
    ],
    "/admin/exams/e1/results",
    (qc) => {
      qc.setQueryData(meKey, me);
      qc.setQueryData(tenantConfigKey, tenantConfig);
    },
  );

describe("results page", () => {
  it("asks for a reason to process before every paper is submitted, with an idempotency key", async () => {
    document.cookie = "sc_csrf=x";
    const sent: { body: unknown; key: string | null }[] = [];
    let processing = false;
    mockApi({
      [`GET ${URL}`]: () => ({
        status: 200,
        body: processing
          ? overview({
              exam_status: "marks_entry_closed",
              run: run({ status: "running", stats: {}, anomalies: [] }),
              actions: actions(),
            })
          : overview({
              exam_status: "marks_entry_closed",
              run: null,
              runs: [],
              unsubmitted: [{ course_code: "UCS301", cohort_code: "COE-2A", status: "open" }],
              actions: actions({ can_process: true }),
            }),
      }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`POST ${URL}/process`]: (_u, init) => {
        sent.push({
          body: JSON.parse(String(init.body)),
          key: new Headers(init.headers).get("Idempotency-Key"),
        });
        processing = true;
        return {
          status: 202,
          body: overview({
            exam_status: "marks_entry_closed",
            run: run({ status: "running", stats: {}, anomalies: [] }),
            actions: actions(),
          }),
        };
      },
    });
    render();
    expect(await screen.findByText("Not every paper is submitted")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Process results" }));
    const dialog = await screen.findByRole("dialog", { name: "Process results?" });
    const confirm = within(dialog).getByRole("button", { name: "Process results" });
    expect(confirm).toBeDisabled(); // a reason is required
    await user.type(within(dialog).getByRole("textbox"), "Faculty confirmed by phone");
    await user.click(confirm);
    expect(await screen.findByText(/Processing results \(revision 1\)/)).toBeInTheDocument();
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toEqual({ override_reason: "Faculty confirmed by phone" });
    expect(sent[0]!.key).toMatch(/^[\w-]{8,}$/);
  });

  it("shows statistics and anomalies, and previews a student's result as they will see it", async () => {
    mockApi({
      [`GET ${URL}`]: () => ({ status: 200, body: overview() }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`GET ${URL}/students`]: (url) => {
        expect(new URLSearchParams(url.split("?")[1]).get("run_id")).toBe("r1");
        return { status: 200, body: { run_id: "r1", items: [student], next_after: null } };
      },
      [`GET ${URL}/students/s1`]: () => ({ status: 200, body: student }),
    });
    render();
    expect(
      (await screen.findByText("Pass rate", { selector: "p" })).parentElement!.parentElement,
    ).toHaveTextContent("66.7%");
    expect(
      screen.getByText(/Revision 1 · processed .* by Priya Malhotra · Scale v2 · 4 students: 2 pass, 1 fail/),
    ).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "50–59%: 1 student" })).toBeInTheDocument();
    expect(screen.getByText("Full marks in every paper")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Asha Rao" }));
    const sheet = await screen.findByRole("dialog", { name: "Result preview" });
    const card = within(sheet).getByRole("article", { name: "Result of Asha Rao" });
    expect(within(card).getByText("SGPA").nextSibling).toHaveTextContent("9");
    expect(within(card).getByText("Percentage").nextSibling).toHaveTextContent("85%");
    // The preview is the student's own view: one card per paper, marks against each component's maximum.
    const paper = within(card).getByText("Data Structures").closest("li")!;
    expect(paper).toHaveTextContent("Internal35 / 40");
    expect(paper).toHaveTextContent("External50 / 60");
    expect(paper).toHaveTextContent("A+");
    expect(within(card).getByText("Passed")).toBeInTheDocument();
  });

  it("lets administrators download a student's issued marksheet and revoke its verification", async () => {
    document.cookie = "sc_csrf=x";
    const pubs = "/api/v1/admin/exams/e1/publications";
    const revoked: unknown[] = [];
    let links = 0;
    mockApi({
      [`GET ${URL}`]: () => ({ status: 200, body: overview({ exam_status: "published" }) }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`GET ${URL}/students`]: () => ({
        status: 200,
        body: { run_id: "r1", items: [student], next_after: null },
      }),
      [`GET ${URL}/students/s1`]: () => ({ status: 200, body: student }),
      [`GET ${pubs}`]: () => ({
        status: 200,
        body: [
          {
            id: "pub1",
            version: 1,
            status: "published",
            scheduled_at: null,
            published_at: "2026-10-07T10:00:00Z",
            withdrawn_at: null,
            withdraw_reason: null,
            students: 4,
            content_hash: "c".repeat(64),
            created_at: "2026-10-07T10:00:00Z",
            marksheets: { total: 4, rendered: 4, pending: 0, failed: 0 },
          },
        ],
      }),
      [`GET ${pubs}/pub1/marksheets/s1`]: () => {
        links += 1;
        return {
          status: 200,
          body: {
            status: "rendered",
            url: `https://files.example/s1.pdf?sig=${links}`,
            filename: "Marksheet-S1.pdf",
            expires_in: 120,
            verification: { code: "7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B", url: "https://verify.example/v/7KQ3" },
          },
        };
      },
      [`POST ${pubs}/pub1/verification/s1/revoke`]: (_u, init) => {
        revoked.push(JSON.parse(String(init.body)));
        return { status: 200, body: { revoked: true } };
      },
    });
    render({ ...admin, permissions: [...admin.permissions, "publications.manage"] });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Asha Rao" }));
    const sheet = await screen.findByRole("dialog", { name: "Published result" });
    const issued = await within(sheet).findByRole("region", { name: "Issued marksheet" });
    expect(issued).toHaveTextContent("7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B");
    await user.click(within(issued).getByRole("button", { name: "Download PDF" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("https://files.example/s1.pdf?sig=2"));

    await user.click(within(issued).getByRole("button", { name: "Revoke verification…" }));
    const confirm = await screen.findByRole("dialog", { name: "Revoke this marksheet's verification?" });
    const button = within(confirm).getByRole("button", { name: "Revoke verification" });
    expect(button).toBeDisabled();
    await user.type(within(confirm).getByRole("textbox"), "Issued to the wrong person");
    await user.click(button);
    await waitFor(() => expect(revoked).toEqual([{ reason: "Issued to the wrong person" }]));
  });

  it("compares sections and drills into a paper's distribution", async () => {
    const bins = (counts: number[]) => counts.map((count, i) => ({ from: i * 10, to: i * 10 + 10, count }));
    const stats = {
      ...STATS,
      stdev_percentage: "24.5",
      papers: [
        {
          ...STATS.papers[0]!,
          median: "50",
          stdev: "24.5",
          histogram: bins([0, 0, 1, 0, 0, 1, 0, 0, 1, 0]),
        },
      ],
      cohorts: [
        {
          cohort_id: "c1",
          code: "COE-1",
          name: "Section 1",
          students: 3,
          appeared: 2,
          passed: 2,
          pass_percentage: "100",
          average_percentage: "67.5",
        },
        {
          cohort_id: "c2",
          code: "COE-2",
          name: "Section 2",
          students: 1,
          appeared: 1,
          passed: 0,
          pass_percentage: "0",
          average_percentage: "25",
        },
      ],
    };
    mockApi({
      [`GET ${URL}`]: () => ({ status: 200, body: overview({ run: run({ stats }) }) }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`GET ${URL}/students`]: () => ({
        status: 200,
        body: { run_id: "r1", items: [student], next_after: null },
      }),
    });
    render();
    expect(await screen.findByText(/median 50% · spread ±24.5/)).toBeInTheDocument();
    const sections = screen.getByRole("table", { name: "Results by section" });
    const weak = within(sections).getByText("COE-2").closest("tr")!;
    expect(weak).toHaveTextContent("Below the exam");
    expect(within(sections).getByText("COE-1").closest("tr")).not.toHaveTextContent("Below the exam");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "UCS301 Data Structures: details" }));
    const sheet = await screen.findByRole("dialog", { name: "UCS301 · Data Structures" });
    expect(within(sheet).getByText("2 of 3 passed")).toBeInTheDocument();
    expect(within(sheet).getByText("median 50 · spread ±24.5")).toBeInTheDocument();
    expect(within(sheet).getByRole("listitem", { name: "80–89%: 1 student" })).toBeInTheDocument();
  });

  it("approves after confirming the password", async () => {
    document.cookie = "sc_csrf=x";
    let reauthed = false;
    const approvals: unknown[] = [];
    mockApi({
      [`GET ${URL}`]: () => ({ status: 200, body: overview() }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`GET ${URL}/students`]: () => ({ status: 200, body: { run_id: "r1", items: [], next_after: null } }),
      "POST /api/v1/auth/reauth": () => {
        reauthed = true;
        return { status: 200, body: {} };
      },
      "GET /api/v1/me": () => ({ status: 200, body: admin }),
      [`POST ${URL}/approve`]: (_u, init) => {
        if (!reauthed)
          return { status: 401, body: { code: "reauth-required", detail: "Confirm your password." } };
        approvals.push(JSON.parse(String(init.body)));
        return {
          status: 200,
          body: overview({
            exam_status: "approved",
            run: run({ status: "approved" }),
            approvals: [
              {
                id: "a1",
                decision: "approved",
                decided_by_name: "Priya Malhotra",
                created_at: "2026-10-07T11:00:00Z",
                comment: null,
                revision: 1,
                content_hash: "b".repeat(64),
              },
            ],
            actions: actions({ can_revoke: true }),
          }),
        };
      },
    });
    render();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Approve results" }));
    const confirm = await screen.findByRole("dialog", { name: "Approve revision 1?" });
    expect(confirm).toHaveTextContent("4 students: 2 pass, 1 fail. Approving locks every paper's marks");
    await user.click(within(confirm).getByRole("button", { name: "Approve results" }));
    const password = await screen.findByLabelText("Password");
    await user.type(password, "my-password-123");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(approvals).toEqual([{ run_id: "r1" }]));
    expect(await screen.findByText(/Priya Malhotra approved revision 1 on/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revoke approval" })).toBeInTheDocument();
  });

  it("explains why the person who processed can't approve in maker-checker mode", async () => {
    mockApi({
      [`GET ${URL}`]: () => ({
        status: 200,
        body: overview({
          approval_mode: "maker_checker",
          actions: actions({
            can_process: true,
            can_reject: true,
            approve_blocked_reason: "Another administrator has to approve results you processed.",
          }),
        }),
      }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`GET ${URL}/students`]: () => ({ status: 200, body: { run_id: "r1", items: [], next_after: null } }),
    });
    render();
    expect(await screen.findByRole("button", { name: "Approve results" })).toBeDisabled();
    expect(
      screen.getByText("Another administrator has to approve results you processed."),
    ).toBeInTheDocument();
  });

  it("flags out-of-date results", async () => {
    mockApi({
      [`GET ${URL}`]: () => ({
        status: 200,
        body: overview({
          exam_status: "marks_entry_closed",
          run: run({ status: "stale" }),
          actions: actions({ can_process: true }),
        }),
      }),
      "GET /api/v1/admin/exams/e1": () => ({ status: 200, body: exam }),
      [`GET ${URL}/students`]: () => ({ status: 200, body: { run_id: "r1", items: [], next_after: null } }),
    });
    render();
    expect(await screen.findByText("These results are out of date")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve results" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Process again" })).toBeInTheDocument();
  });
});
