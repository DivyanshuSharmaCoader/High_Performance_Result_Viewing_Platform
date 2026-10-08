import type {
  Marksheet,
  Me,
  MyResult,
  MyResultItem,
  Publication,
  ResultPayload,
} from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReauthProvider } from "../components/reauth";
import { StudentShell } from "../components/student-shell";
import { PublishPanel } from "../features/results/publish";
import StudentHome from "../features/student/home";
import StudentResultPage from "../features/student/result";
import { meKey } from "../lib/session";
import { TenantProvider, tenantConfigKey } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

vi.mock("../lib/navigate", () => ({ goTo: vi.fn() }));
import { goTo } from "../lib/navigate";

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

const payload: ResultPayload = {
  schema: 1,
  institution: { name: "Demo Public School", display_name: "Demo Public School" },
  exam: { name: "Half-yearly", kind: "term", term: "Term 1", session: "2025-26" },
  scheme: { name: "Board 9-point", strategy: "percentage_bands" },
  student: {
    enrollment_no: "102401001",
    full_name: "Aarav Gupta",
    cohort: { code: "X-A", name: "Class X A" },
    program: null,
  },
  result: {
    outcome: "pass",
    total: "170",
    max_total: "200",
    percentage: "85",
    grade: "A2",
    grade_point: "9",
    sgpa: null,
    credits_attempted: null,
    credits_earned: null,
    rank: null,
    notes: [],
  },
  papers: [
    {
      course_code: "MATH",
      course_name: "Mathematics",
      credits: null,
      attendance: "present",
      outcome: "pass",
      total: "88",
      max_total: "100",
      percentage: "88",
      grade: "A2",
      grade_point: "9",
      failed_components: [],
      missing_components: [],
      components: [
        { code: "INT", label: "Internal", max: "20", marks: "18" },
        { code: "TH", label: "Theory", max: "80", marks: "70" },
      ],
    },
    {
      course_code: "SCI",
      course_name: "Science",
      credits: null,
      attendance: "absent",
      outcome: "absent",
      total: null,
      max_total: "100",
      percentage: null,
      grade: "AB",
      grade_point: null,
      failed_components: [],
      missing_components: [],
      components: [{ code: "TH", label: "Theory", max: "100", marks: null }],
    },
  ],
};

const verification = {
  code: "7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B",
  url: "https://verify.scorecode.in/v/7KQ3M9XDPA2F8RTCWV6HQ7MN2B",
};
const marksheet = (status: Marksheet["status"], url: string | null = null): Marksheet => ({
  status,
  url,
  filename: url ? "Marksheet-102401001-Half-yearly-2025-26.pdf" : null,
  expires_in: url ? 120 : null,
  verification,
});

const item = (id: string, name: string, extra: Partial<MyResultItem> = {}): MyResultItem => ({
  publication_id: id,
  published_at: "2026-10-07T10:00:00Z",
  revised: false,
  exam: { ...payload.exam, name },
  outcome: "pass",
  percentage: "85",
  grade: "A2",
  sgpa: null,
  ...extra,
});

const studentRoutes = (path: string) =>
  renderRoutes(
    [
      {
        path: "/me",
        element: (
          <TenantProvider>
            <StudentShell>
              <StudentHome />
            </StudentShell>
          </TenantProvider>
        ),
      },
      {
        path: "/me/results/:publicationId",
        element: (
          <TenantProvider>
            <StudentResultPage />
          </TenantProvider>
        ),
      },
      { path: "/me/account", element: <p>Account page</p> },
    ],
    path,
    (qc) => {
      qc.setQueryData(meKey, student);
      qc.setQueryData(tenantConfigKey, tenantConfig);
    },
  );

describe("student portal", () => {
  it("leads with the latest result and lists the earlier ones", async () => {
    mockApi({
      "GET /api/v1/me/results": () => ({
        status: 200,
        body: [
          item("p2", "Half-yearly", { revised: true }),
          item("p1", "Unit test 1", { percentage: "72", outcome: "fail" }),
        ],
      }),
    });
    studentRoutes("/me");
    const latest = await screen.findByRole("link", { name: /Latest result/ });
    expect(latest).toHaveTextContent("Half-yearly");
    expect(latest).toHaveTextContent("Passed");
    expect(latest).toHaveTextContent("85%");
    expect(latest).toHaveTextContent("revised");
    expect(latest).toHaveAttribute("href", "/me/results/p2");
    const earlier = screen.getByRole("link", { name: /Unit test 1/ });
    expect(earlier).toHaveTextContent("72%");
    expect(earlier).toHaveTextContent("Not passed");
  });

  it("says when nothing is published yet", async () => {
    mockApi({ "GET /api/v1/me/results": () => ({ status: 200, body: [] }) });
    studentRoutes("/me");
    expect(await screen.findByText("No results yet")).toBeInTheDocument();
    expect(screen.getByText(/as soon as .* publishes them/)).toBeInTheDocument();
  });

  it("shows the full result with marks per paper and the class average when shared", async () => {
    mockApi({
      "GET /api/v1/me/results/p2": () => ({
        status: 200,
        body: {
          publication_id: "p2",
          version: 2,
          published_at: "2026-10-07T10:00:00Z",
          revised: true,
          payload,
        } satisfies MyResult,
      }),
      "GET /api/v1/me/results/p2/marksheet": () => ({ status: 200, body: marksheet("pending") }),
      "GET /api/v1/me/results/p2/stats": () => ({
        status: 200,
        body: {
          available: true,
          stats: {
            average_percentage: "61.5",
            papers: [{ course_code: "MATH", average: "64.2", max_total: "100" }],
          },
        },
      }),
    });
    studentRoutes("/me/results/p2");
    const result = await screen.findByRole("article", { name: "Result of Aarav Gupta" });
    expect(within(result).getByText("Passed")).toBeInTheDocument();
    expect(within(result).getByText("Percentage").nextSibling).toHaveTextContent("85%");
    const maths = within(result).getByText("Mathematics").closest("li")!;
    expect(maths).toHaveTextContent("Internal18 / 20");
    expect(maths).toHaveTextContent("class average 64.2");
    const science = within(result).getByText("Science").closest("li")!;
    expect(science).toHaveTextContent("Absent");
    expect(screen.getByText(/This is a revised result/)).toBeInTheDocument();
    expect(await screen.findByText(/class average 61.5%/)).toBeInTheDocument();
  });

  it("downloads the marksheet through a fresh signed link and shares a verification link", async () => {
    let calls = 0;
    mockApi({
      "GET /api/v1/me/results/p2": () => ({
        status: 200,
        body: {
          publication_id: "p2",
          version: 1,
          published_at: "2026-10-07T10:00:00Z",
          revised: false,
          payload,
        },
      }),
      "GET /api/v1/me/results/p2/stats": () => ({ status: 200, body: { available: false } }),
      "GET /api/v1/me/results/p2/marksheet": () => {
        calls += 1;
        return { status: 200, body: marksheet("rendered", `https://files.example/m.pdf?sig=${calls}`) };
      },
    });
    const user = userEvent.setup();
    studentRoutes("/me/results/p2");
    const download = await screen.findByRole("button", { name: "Download" });
    expect(screen.getByText(/QR code anyone can scan/)).toBeInTheDocument();
    await user.click(download);
    // The link shown at page load may have expired: the click asks for a new one.
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("https://files.example/m.pdf?sig=2"));
    expect(screen.getByText("verify.scorecode.in/v/7KQ3M9XDPA2F8RTCWV6HQ7MN2B")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe(verification.url);
  });

  it("says when the marksheet is still being prepared", async () => {
    mockApi({
      "GET /api/v1/me/results/p2": () => ({
        status: 200,
        body: {
          publication_id: "p2",
          version: 1,
          published_at: "2026-10-07T10:00:00Z",
          revised: false,
          payload,
        },
      }),
      "GET /api/v1/me/results/p2/stats": () => ({ status: 200, body: { available: false } }),
      "GET /api/v1/me/results/p2/marksheet": () => ({ status: 200, body: marksheet("pending") }),
    });
    studentRoutes("/me/results/p2");
    expect(await screen.findByText(/Being prepared/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preparing/ })).toBeDisabled();
    // The verification code exists from publication, so it can be shared straight away.
    expect(screen.getByText(verification.code)).toBeInTheDocument();
  });

  it("explains a withdrawn or missing result kindly", async () => {
    mockApi({
      "GET /api/v1/me/results/gone": () => ({
        status: 404,
        body: { code: "not-found", detail: "Result not found" },
      }),
      "GET /api/v1/me/results/gone/stats": () => ({ status: 404, body: { code: "not-found", detail: "x" } }),
      "GET /api/v1/me/results/gone/marksheet": () => ({
        status: 404,
        body: { code: "not-found", detail: "x" },
      }),
    });
    studentRoutes("/me/results/gone");
    expect(await screen.findByText(/may have been withdrawn by your institution/)).toBeInTheDocument();
  });

  it("has a light account menu that closes with Escape", async () => {
    mockApi({ "GET /api/v1/me/results": () => ({ status: 200, body: [] }) });
    studentRoutes("/me");
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Account menu" });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(button.getAttribute("aria-controls")!)!;
    expect(panel).toHaveTextContent("Aarav Gupta102401001");
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
    await user.click(button);
    await user.click(screen.getByRole("button", { name: /Password & sessions/ }));
    expect(await screen.findByText("Account page")).toBeInTheDocument();
  });
});

const pub = (extra: Partial<Publication> = {}): Publication => ({
  id: "pub1",
  version: 1,
  status: "published",
  scheduled_at: null,
  published_at: "2026-10-07T10:00:00Z",
  withdrawn_at: null,
  withdraw_reason: null,
  students: 120,
  content_hash: "c".repeat(64),
  created_at: "2026-10-07T10:00:00Z",
  ...extra,
});

describe("publication panel", () => {
  const admin: Me = {
    ...ownerMe,
    permissions: [...ownerMe.permissions, "publications.manage"],
    features: {},
  };
  const render = (status: string, me: Me = admin) =>
    renderRoutes(
      [
        {
          path: "/",
          element: (
            <ReauthProvider>
              <PublishPanel examId="e1" examStatus={status} students={120} />
            </ReauthProvider>
          ),
        },
      ],
      "/",
      (qc) => qc.setQueryData(meKey, me),
    );

  it("publishes approved results with an idempotency key after confirming", async () => {
    document.cookie = "sc_csrf=x";
    const keys: (string | null)[] = [];
    let published = false;
    mockApi({
      "GET /api/v1/admin/exams/e1/publications": () => ({ status: 200, body: published ? [pub()] : [] }),
      "POST /api/v1/admin/exams/e1/publications": (_u, init) => {
        keys.push(new Headers(init.headers).get("Idempotency-Key"));
        published = true;
        return { status: 201, body: pub() };
      },
    });
    render("approved");
    expect(await screen.findByText(/Approved and ready/)).toBeInTheDocument();
    // Scheduling isn't in this plan: the button says so and points to the plans.
    expect(screen.getByRole("button", { name: "Schedule…" })).toBeDisabled();
    expect(screen.getByRole("link", { name: /Scheduling comes with Growth and Pro/ })).toHaveAttribute(
      "href",
      "/admin/plan",
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Publish now" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish to 120 students now?" });
    await user.click(within(dialog).getByRole("button", { name: "Publish now" }));
    await waitFor(() => expect(keys).toHaveLength(1));
    expect(keys[0]).toMatch(/^[\w-]{8,}$/);
  });

  it("follows marksheet preparation and retries the ones that failed", async () => {
    document.cookie = "sc_csrf=x";
    let retried = false;
    mockApi({
      "GET /api/v1/admin/exams/e1/publications": () => ({
        status: 200,
        body: [
          pub({
            marksheets: retried
              ? { total: 120, rendered: 117, pending: 3, failed: 0 }
              : { total: 120, rendered: 117, pending: 0, failed: 3 },
          }),
        ],
      }),
      "POST /api/v1/admin/exams/e1/publications/pub1/marksheets/retry": () => {
        retried = true;
        return { status: 200, body: { queued: 3 } };
      },
    });
    render("published");
    expect(await screen.findByText("3 of 120 marksheets couldn't be prepared")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Preparing marksheet PDFs…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Marksheets prepared" })).toHaveAttribute(
      "aria-valuenow",
      "98",
    );
    expect(screen.getByText("117 of 120")).toBeInTheDocument();
  });

  it("says when every marksheet is ready", async () => {
    mockApi({
      "GET /api/v1/admin/exams/e1/publications": () => ({
        status: 200,
        body: [pub({ marksheets: { total: 120, rendered: 120, pending: 0, failed: 0 } })],
      }),
    });
    render("published");
    expect(await screen.findByText(/All 120 marksheets are ready/)).toBeInTheDocument();
  });

  it("withdraws live results only with a reason", async () => {
    document.cookie = "sc_csrf=x";
    const bodies: unknown[] = [];
    mockApi({
      "GET /api/v1/admin/exams/e1/publications": () => ({ status: 200, body: [pub()] }),
      "POST /api/v1/admin/exams/e1/publications/pub1/withdraw": (_u, init) => {
        bodies.push(JSON.parse(String(init.body)));
        return { status: 200, body: pub({ status: "withdrawn", withdraw_reason: "Wrong cohort" }) };
      },
    });
    render("published");
    expect(await screen.findByText(/Live since/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Withdraw" }));
    const dialog = await screen.findByRole("dialog", { name: "Withdraw these results?" });
    const confirm = within(dialog).getByRole("button", { name: "Withdraw results" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox"), "Wrong cohort");
    await user.click(confirm);
    await waitFor(() => expect(bodies).toEqual([{ reason: "Wrong cohort" }]));
  });
});
