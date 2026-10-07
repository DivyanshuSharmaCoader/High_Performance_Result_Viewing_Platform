import type { MarkSheet, Me } from "@scorecode/api-client";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  attendanceOf,
  cellError,
  changeFor,
  liveTotal,
  parseClipboard,
  rowFromServer,
} from "../features/marks/logic";
import MarkSheetPage from "../features/marks/sheet";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

const faculty: Me = {
  ...ownerMe,
  roles: ["faculty"],
  permissions: ["exams.view_assigned", "marks.enter_assigned"],
};
const INT = { code: "INT", label: "Internal", max: "40.00", min_pass: null };
const EXT = { code: "EXT", label: "External", max: "60.00", min_pass: "21.00" };

const sheet = (extra: Partial<MarkSheet> = {}): MarkSheet => ({
  exam_id: "e1",
  exam_name: "Finals",
  exam_status: "marks_entry_open",
  marks_deadline: null,
  paper_id: "p1",
  course_code: "UCS301",
  course_name: "Data Structures",
  components: [INT, EXT],
  max_total: "100.00",
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
  students: [
    {
      student_id: "s1",
      enrollment_no: "A001",
      full_name: "Asha Rao",
      entry: {
        components: { INT: "30", EXT: "40" },
        attendance: "present",
        total: "70.00",
        version: 3,
        complete: true,
        updated_at: "2026-10-07T10:00:00Z",
        updated_by_name: "Faculty Person",
      },
    },
    { student_id: "s2", enrollment_no: "A002", full_name: "Bilal Khan", entry: null },
    { student_id: "s3", enrollment_no: "A003", full_name: "Chitra Iyer", entry: null },
  ],
  ...extra,
});

describe("mark cell rules", () => {
  it("validates, recognises codes and builds requests", () => {
    expect(cellError("40", INT)).toBeNull();
    expect(cellError("40.5", INT)).toBe("Out of 40");
    expect(cellError("12.125", INT)).toBe("At most two decimal places");
    expect(cellError("ten", INT)).toMatch(/Enter a number/);
    expect(cellError("ab", INT)).toBeNull();
    expect(attendanceOf({ INT: "AB", EXT: "AB" })).toBe("absent");
    expect(attendanceOf({ INT: "12", EXT: "" })).toBe("present");
    expect(parseClipboard("12\t30\r\n15\t41\r\n")).toEqual([
      ["12", "30"],
      ["15", "41"],
    ]);
    const row = rowFromServer(sheet(), "s1");
    expect(row.values).toEqual({ INT: "30", EXT: "40" });
    expect(changeFor("s1", { ...row, values: { INT: "31", EXT: "" } })).toEqual({
      student_id: "s1",
      attendance: "present",
      version: 3,
      components: { INT: "31", EXT: null },
    });
    expect(
      changeFor("s2", { ...rowFromServer(sheet(), "s2"), values: { INT: "MP", EXT: "MP" } }).components,
    ).toEqual({});
    expect(liveTotal({ ...row, values: { INT: "12.5", EXT: "30" } }, [INT, EXT])).toBe("42.5");
    expect(liveTotal({ ...row, values: { INT: "12.5", EXT: "" } }, [INT, EXT])).toBe("");
  });
});

describe("mark sheet", () => {
  const path = "/marking/e1/p1/c1";
  const url = "/api/v1/exams/e1/papers/p1/cohorts/c1/marks";
  const render = () =>
    renderRoutes([{ path: "/marking/:examId/:paperId/:cohortId", element: <MarkSheetPage /> }], path, (qc) =>
      qc.setQueryData(meKey, faculty),
    );

  it("autosaves typed marks with the version they were based on", async () => {
    document.cookie = "sc_csrf=x";
    const puts: unknown[] = [];
    mockApi({
      [`GET ${url}`]: () => ({ status: 200, body: sheet() }),
      [`PUT ${url}`]: (_u, init) => {
        const body = JSON.parse(String(init.body));
        puts.push(body);
        return {
          status: 200,
          body: body.changes.map((c: { student_id: string; version: number | null }) => ({
            student_id: c.student_id,
            entry: {
              components: { INT: "31", EXT: "40" },
              attendance: "present",
              total: "71.00",
              version: (c.version ?? 0) + 1,
              complete: true,
              updated_at: "2026-10-07T10:01:00Z",
              updated_by_name: "Faculty Person",
            },
          })),
        };
      },
    });
    render();
    const cell = await screen.findByRole("textbox", { name: "A001 Internal" });
    expect(cell).toHaveValue("30");
    await userEvent.clear(cell);
    await userEvent.type(cell, "31");
    expect(screen.getByRole("status")).toHaveTextContent("1 unsaved");
    await waitFor(() => expect(puts).toHaveLength(1), { timeout: 3000 });
    expect(puts[0]).toEqual({
      changes: [
        { student_id: "s1", attendance: "present", version: 3, components: { INT: "31", EXT: "40" } },
      ],
    });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("All changes saved"));
    await userEvent.type(cell, "{enter}");
    expect(screen.getByRole("textbox", { name: "A002 Internal" })).toHaveFocus();
  });

  it("pastes a block from Excel and flags invalid cells instead of saving them", async () => {
    document.cookie = "sc_csrf=x";
    const puts: { changes: { student_id: string }[] }[] = [];
    mockApi({
      [`GET ${url}`]: () => ({ status: 200, body: sheet() }),
      [`PUT ${url}`]: (_u, init) => {
        puts.push(JSON.parse(String(init.body)));
        return { status: 200, body: [] };
      },
    });
    render();
    const start = await screen.findByRole("textbox", { name: "A002 Internal" });
    fireEvent.paste(start, { clipboardData: { getData: () => "12\t50\n55\tAB\n" } });
    expect(screen.getByRole("textbox", { name: "A002 External" })).toHaveValue("50");
    const bad = screen.getByRole("textbox", { name: "A003 Internal" });
    expect(bad).toHaveValue("55");
    expect(bad).toHaveAttribute("aria-invalid", "true"); // 55 is more than 40
    expect(bad).toHaveAttribute("title", "Out of 40");
    const mixed = screen.getByRole("textbox", { name: "A003 External" });
    expect(mixed).toHaveValue("AB"); // kept as typed, not spread over the 55
    expect(mixed.getAttribute("title")).toMatch(/applies to the whole paper/);
    await waitFor(() => expect(puts).toHaveLength(1), { timeout: 3000 });
    expect(puts[0]!.changes.map((c) => c.student_id)).toEqual(["s2"]); // the invalid row stays unsaved
    expect(screen.getByRole("status")).toHaveTextContent("1 to fix");
  });

  it("shows a conflict when someone else saved first and loads their values", async () => {
    document.cookie = "sc_csrf=x";
    let gets = 0;
    mockApi({
      [`GET ${url}`]: () => {
        gets += 1;
        if (gets === 1) return { status: 200, body: sheet() };
        const fresh = sheet();
        fresh.students[0]!.entry = {
          ...fresh.students[0]!.entry!,
          components: { INT: "35", EXT: "40" },
          version: 4,
        };
        return { status: 200, body: fresh };
      },
      [`PUT ${url}`]: () => ({
        status: 409,
        body: {
          code: "conflict",
          title: "Conflict",
          detail: "Someone else changed some of these marks.",
          conflicts: [{ student_id: "s1", current_version: 4 }],
        },
      }),
    });
    render();
    const cell = await screen.findByRole("textbox", { name: "A001 Internal" });
    await userEvent.clear(cell);
    await userEvent.type(cell, "33");
    await waitFor(() => expect(screen.getByRole("textbox", { name: "A001 Internal" })).toHaveValue("35"), {
      timeout: 3000,
    });
    const row = screen.getByRole("textbox", { name: "A001 Internal" }).closest("tr")!;
    expect(
      within(row).getByText(/Someone else saved this row first\. Your entry \(33 \/ 40\) was not saved\./),
    ).toBeInTheDocument();
  });

  it("is read-only once submitted", async () => {
    mockApi({
      [`GET ${url}`]: () => ({
        status: 200,
        body: sheet({
          submission_status: "submitted",
          can_edit: false,
          can_submit: false,
          submitted_by_name: "Faculty Person",
        }),
      }),
    });
    render();
    expect(await screen.findByRole("textbox", { name: "A001 Internal" })).toHaveAttribute("readonly");
    expect(screen.getByText(/Faculty Person submitted these marks/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit paper" })).not.toBeInTheDocument();
  });

  it("never starts the grid from a cached copy: marks saved or imported since are shown", async () => {
    const fresh = sheet();
    fresh.students[1]!.entry = {
      components: { INT: "22", EXT: "33" },
      attendance: "present",
      total: "55.00",
      version: 1,
      complete: true,
      updated_at: "2026-10-07T11:00:00Z",
      updated_by_name: "An import",
    };
    mockApi({ [`GET ${url}`]: () => ({ status: 200, body: fresh }) });
    renderRoutes(
      [{ path: "/marking/:examId/:paperId/:cohortId", element: <MarkSheetPage /> }],
      path,
      (qc) => {
        qc.setQueryData(meKey, faculty);
        qc.setQueryData(["marks", "sheet", url], sheet()); // from an earlier visit, before the import
      },
    );
    expect(await screen.findByRole("textbox", { name: "A002 Internal" })).toHaveValue("22");
    expect(screen.getByRole("textbox", { name: "A002 External" })).toHaveValue("33");
  });
});
