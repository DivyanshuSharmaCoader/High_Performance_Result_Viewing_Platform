import type { ActivationCodes, IssuedCode } from "@scorecode/api-client";
import {
  Button,
  Callout,
  Dialog,
  DialogContent,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Th,
  TenantMark,
  formatDate,
  pluralize,
} from "@scorecode/ui";
import { Download, Printer } from "lucide-react";
import { createPortal } from "react-dom";

import { useTenant } from "../../lib/tenant";

const SKIP_REASON: Record<string, string> = {
  already_active: "already activated",
  has_code: "already have an unused code",
  not_active_student: "aren't active students",
};

export function activationUrl(): string {
  return `${window.location.origin}/activate`;
}

/** CSV with spreadsheet-formula protection: a cell that starts with = + - @ is prefixed with '. */
export function slipsCsv(codes: IssuedCode[]): string {
  const cell = (v: string | null | undefined) => {
    let s = v ?? "";
    if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
    return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  const url = activationUrl();
  const lines = [
    ["Enrollment no.", "Name", "Cohort", "Activation code", "Valid until", "Activate at"].join(","),
    ...codes.map((c) =>
      [c.enrollment_no, c.full_name, c.cohort_code, c.code, c.expires_at.slice(0, 10), url]
        .map(cell)
        .join(","),
    ),
  ];
  return lines.join("\r\n") + "\r\n";
}

export function downloadCsv(codes: IssuedCode[], name: string): void {
  const blob = new Blob(["﻿" + slipsCsv(codes)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The printable sheet: rendered outside the app shell and shown only when printing. */
export function PrintableSlips({ codes }: { codes: IssuedCode[] }) {
  const { branding } = useTenant();
  const url = activationUrl();
  return createPortal(
    <div className="print-only" aria-hidden>
      <div className="grid grid-cols-2 gap-4 text-black">
        {codes.map((c) => (
          <article
            key={c.student_id}
            className="break-inside-avoid rounded-lg border border-dashed border-neutral-400 p-4"
          >
            <header className="mb-3 flex items-center gap-2 border-b border-neutral-200 pb-2">
              <TenantMark name={branding.display_name} logoUrl={branding.logo_url} size={24} />
              <p className="text-[12px] font-semibold">{branding.display_name}</p>
            </header>
            <p className="text-[15px] font-semibold">{c.full_name}</p>
            <p className="text-[12px]">
              Enrollment no. <span className="font-mono font-semibold">{c.enrollment_no}</span>
              {c.cohort_code && <> · {c.cohort_code}</>}
            </p>
            <p className="mt-3 text-[11px] uppercase tracking-wide text-neutral-600">Activation code</p>
            <p className="font-mono text-[22px] font-bold tracking-[0.15em]">{c.code}</p>
            <ol className="mt-3 list-decimal space-y-0.5 pl-4 text-[11px] leading-snug">
              <li>
                Go to <span className="font-semibold">{url}</span>
              </li>
              <li>Enter your enrollment number and this code, then choose a password.</li>
              <li>Keep this slip private. The code works once, until {formatDate(c.expires_at)}.</li>
            </ol>
          </article>
        ))}
      </div>
    </div>,
    document.body,
  );
}

export function SlipsSummary({ result }: { result: ActivationCodes }) {
  const groups = Object.entries(
    result.skipped.reduce<Record<string, number>>((acc, s) => {
      acc[s.reason] = (acc[s.reason] ?? 0) + 1;
      return acc;
    }, {}),
  );
  if (groups.length === 0) return null;
  return (
    <p className="text-[13px] text-fg-subtle">
      Skipped{" "}
      {groups.map(([reason, n], i) => (
        <span key={reason}>
          {i > 0 && (i === groups.length - 1 ? " and " : ", ")}
          {pluralize(n, "student")} who {SKIP_REASON[reason] ?? reason}
        </span>
      ))}
      .
    </p>
  );
}

export function SlipsActions({ result, fileName }: { result: ActivationCodes; fileName: string }) {
  return (
    <>
      <Button
        variant="secondary"
        leadingIcon={<Download />}
        onClick={() => downloadCsv(result.issued, fileName)}
      >
        Download CSV
      </Button>
      <Button leadingIcon={<Printer />} onClick={() => window.print()}>
        Print {pluralize(result.issued.length, "slip")}
      </Button>
    </>
  );
}

export function CodesTable({ codes }: { codes: IssuedCode[] }) {
  return (
    <TableContainer>
      <Table>
        <THead>
          <tr>
            <Th>Student</Th>
            <Th>Enrollment no.</Th>
            <Th>Code</Th>
          </tr>
        </THead>
        <TBody>
          {codes.map((c) => (
            <tr key={c.student_id}>
              <Td className="max-w-0 truncate">{c.full_name}</Td>
              <Td className="whitespace-nowrap font-mono text-[13px]">{c.enrollment_no}</Td>
              <Td className="whitespace-nowrap font-mono text-[13px] font-semibold tracking-wider">
                {c.code}
              </Td>
            </tr>
          ))}
        </TBody>
      </Table>
    </TableContainer>
  );
}

/** Codes for one or a few students (from the student page). */
export function SlipsDialog({ codes, onClose }: { codes: ActivationCodes; onClose: () => void }) {
  const first = codes.issued[0];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={
          codes.issued.length === 1 && first ? `Activation code for ${first.full_name}` : "Activation codes"
        }
        description="Give the student their slip. They'll use it once to choose a password."
        footer={
          <SlipsActions
            result={codes}
            fileName={`activation-code-${first?.enrollment_no ?? "students"}.csv`}
          />
        }
      >
        <div className="flex flex-col gap-4">
          <Callout tone="warning" title="Shown only now">
            ScoreCode stores only a fingerprint of each code. Print or download it before closing — if
            it&apos;s lost, issue a new one.
          </Callout>
          {codes.issued.length === 1 && first ? (
            <div className="rounded-lg border border-border bg-surface-2/40 p-4 text-center">
              <p className="text-[13px] text-fg-subtle">
                Enrollment no. <span className="font-mono text-fg">{first.enrollment_no}</span>
              </p>
              <p className="mt-1 font-mono text-2xl font-bold tracking-[0.15em] text-fg">{first.code}</p>
              <p className="mt-1 text-[13px] text-fg-subtle">
                Valid until {formatDate(first.expires_at)} · {activationUrl()}
              </p>
            </div>
          ) : (
            <CodesTable codes={codes.issued} />
          )}
          <SlipsSummary result={codes} />
        </div>
        <PrintableSlips codes={codes.issued} />
      </DialogContent>
    </Dialog>
  );
}
