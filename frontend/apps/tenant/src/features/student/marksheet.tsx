import { ApiError } from "@scorecode/api-client";
import { Button } from "@scorecode/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { goTo } from "../../lib/navigate";
import { fetchMyMarksheet, myMarksheetKey, useMyMarksheet } from "./api";

/**
 * The official PDF and how to prove it's genuine. Download links are signed and expire in two minutes,
 * so a fresh one is fetched on every click rather than reused from the page.
 */
export function MarksheetCard({ publicationId }: { publicationId: string }) {
  const qc = useQueryClient();
  const q = useMyMarksheet(publicationId);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  if (!q.data) return null;
  const m = q.data;

  const download = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const fresh = await qc.fetchQuery({
        queryKey: myMarksheetKey(publicationId),
        queryFn: () => fetchMyMarksheet(publicationId),
        staleTime: 0,
      });
      if (fresh.url) goTo(fresh.url);
      else setProblem("Your marksheet is still being prepared. Try again in a minute.");
    } catch (e) {
      setProblem(
        e instanceof ApiError && e.status === 404
          ? "This marksheet is no longer available."
          : "The download didn't start. Check your connection and try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    if (!m.verification) return;
    try {
      await navigator.clipboard.writeText(m.verification.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setProblem("Couldn't copy the link. Select it and copy it yourself.");
    }
  };

  const status =
    m.status === "rendered"
      ? "Your official statement of marks, with a QR code anyone can scan to check it."
      : m.status === "pending"
        ? "Being prepared — it'll be ready in a moment."
        : "Not ready yet. Your institution can see this and will fix it.";
  return (
    <section
      aria-labelledby="marksheet-title"
      className="mt-5 rounded-2xl border border-border bg-surface p-4 sm:p-5 print:hidden"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 id="marksheet-title" className="text-sm font-semibold text-fg">
            Marksheet (PDF)
          </h2>
          <p className="text-[13px] text-fg-muted" aria-live="polite">
            {status}
          </p>
        </div>
        <Button
          leadingIcon={<Download />}
          loading={busy || m.status === "pending"}
          disabled={m.status !== "rendered"}
          onClick={() => void download()}
        >
          {m.status === "pending" ? "Preparing…" : "Download"}
        </Button>
      </div>
      {problem && (
        <p role="alert" className="mt-3 text-[13px] text-danger">
          {problem}
        </p>
      )}
      {m.verification && (
        <div className="mt-4 border-t border-border pt-4">
          <p className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
            <ShieldCheck className="size-4 text-success" aria-hidden /> Share a verifiable result
          </p>
          <p className="mt-0.5 text-[12px] text-fg-subtle">
            Employers and universities can confirm it's genuine at this address. They see your institution,
            the exam and whether the result is current — not your marks.
          </p>
          <div className="mt-2 flex items-center gap-2 rounded-lg bg-surface-2 py-1.5 pr-1.5 pl-3">
            <code className="min-w-0 flex-1 truncate font-mono text-[12px] text-fg-muted">
              {m.verification.url.replace(/^https?:\/\//, "")}
            </code>
            <Button
              size="sm"
              variant="ghost"
              leadingIcon={copied ? <Check /> : <Copy />}
              onClick={() => void copy()}
            >
              {copied ? "Copied" : "Copy link"}
            </Button>
          </div>
          <p className="mt-1.5 text-[12px] text-fg-subtle">
            Verification code <span className="font-mono">{m.verification.code}</span>
          </p>
        </div>
      )}
    </section>
  );
}
