import type { Attendance, MarkSheet } from "@scorecode/api-client";

/** Codes staff type into a mark cell instead of a number (the tenant's defaults). */
export const CODES: Record<string, Attendance> = {
  AB: "absent",
  EX: "exempt",
  MP: "malpractice",
  WH: "withheld",
};
export const CODE_OF: Record<Attendance, string> = {
  present: "",
  absent: "AB",
  exempt: "EX",
  malpractice: "MP",
  withheld: "WH",
};

export interface RowState {
  values: Record<string, string>; // what's in the cells (numbers as typed, or a code)
  attendance: Attendance;
  version: number | null;
  total: string | null;
  status: "saved" | "dirty" | "saving" | "error" | "conflict";
  errors: Record<string, string>;
  note?: string;
}

type Component = MarkSheet["components"][number];

/** Validate one cell. Returns an error message, or null when the text is a valid mark, a code or blank. */
export function cellError(text: string, component: Component): string | null {
  const t = text.trim();
  if (t === "" || CODES[t.toUpperCase()]) return null;
  if (!/^\d+(\.\d+)?$/.test(t)) return "Enter a number, or AB, EX, MP or WH";
  if (/\.\d{3,}$/.test(t)) return "At most two decimal places";
  if (Number(t) > Number(component.max)) return `Out of ${trimNum(component.max)}`;
  return null;
}

export function trimNum(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

/** Row attendance implied by the cells: any code wins (a whole-paper status), otherwise present. */
export function attendanceOf(values: Record<string, string>): Attendance {
  for (const v of Object.values(values)) {
    const code = CODES[v.trim().toUpperCase()];
    if (code) return code;
  }
  return "present";
}

export function rowFromServer(sheet: MarkSheet, studentId: string): RowState {
  const student = sheet.students.find((s) => s.student_id === studentId);
  const entry = student?.entry;
  const values: Record<string, string> = {};
  for (const c of sheet.components) values[c.code] = "";
  if (entry) {
    if (entry.attendance !== "present") {
      for (const c of sheet.components) values[c.code] = CODE_OF[entry.attendance];
    } else {
      for (const [k, v] of Object.entries(entry.components)) values[k] = trimNum(v);
    }
  }
  return {
    values,
    attendance: entry?.attendance ?? "present",
    version: entry?.version ?? null,
    total: entry?.total ?? null,
    status: "saved",
    errors: {},
  };
}

/** The request body for one row (only valid rows are sent). */
export function changeFor(studentId: string, row: RowState) {
  const attendance = attendanceOf(row.values);
  return {
    student_id: studentId,
    attendance,
    version: row.version,
    components:
      attendance === "present"
        ? Object.fromEntries(
            Object.entries(row.values).map(([k, v]) => [k, v.trim() === "" ? null : v.trim()]),
          )
        : {},
  };
}

/** Clipboard text (Excel/Sheets copy = tab-separated rows) → a grid of cells. */
export function parseClipboard(text: string): string[][] {
  const lines = text.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n");
  return lines.map((l) => l.split("\t").map((c) => c.trim()));
}

/** Running total shown while typing (the server's total is authoritative once saved). */
export function liveTotal(row: RowState, components: Component[]): string {
  if (attendanceOf(row.values) !== "present") return CODE_OF[attendanceOf(row.values)];
  let sum = 0;
  for (const c of components) {
    const v = row.values[c.code]?.trim() ?? "";
    if (v === "" || cellError(v, c)) return "";
    sum += Number(v);
  }
  return trimNum(sum.toFixed(2));
}
