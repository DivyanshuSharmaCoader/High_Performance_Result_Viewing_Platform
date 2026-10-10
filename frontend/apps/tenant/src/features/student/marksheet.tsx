import { ApiError } from "@scorecode/api-client";
import { Button } from "@scorecode/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useI18n } from "../../lib/i18n";
import { goTo } from "../../lib/navigate";
import { fetchMyMarksheet, myMarksheetKey, useMyMarksheet } from "./api";

/**
 * The official PDF and how to prove it's genuine. Download links are signed and expire in two minutes,
 * so a fresh one is fetched on every click rather than reused from the page.
 */
export function MarksheetCard({ publicationId }: { publicationId: string }) {
  const { t } = useI18n();
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
      else setProblem(t("ms.still_preparing"));
    } catch (e) {
      setProblem(e instanceof ApiError && e.status === 404 ? t("ms.gone") : t("ms.download_failed"));
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
      setProblem(t("ms.copy_failed"));
    }
  };

  const status =
    m.status === "rendered" ? t("ms.ready") : m.status === "pending" ? t("ms.pending") : t("ms.failed");
  return (
    <section
      aria-labelledby="marksheet-title"
      className="mt-5 rounded-2xl border border-border bg-surface p-4 sm:p-5 print:hidden"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 id="marksheet-title" className="text-sm font-semibold text-fg">
            {t("ms.title")}
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
          {m.status === "pending" ? t("ms.preparing") : t("ms.download")}
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
            <ShieldCheck className="size-4 text-success" aria-hidden /> {t("ms.share_title")}
          </p>
          <p className="mt-0.5 text-[12px] text-fg-subtle">{t("ms.share_desc")}</p>
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
              {copied ? t("ms.copied") : t("ms.copy")}
            </Button>
          </div>
          <p className="mt-1.5 text-[12px] text-fg-subtle">
            {t("ms.code")} <span className="font-mono">{m.verification.code}</span>
          </p>
        </div>
      )}
    </section>
  );
}
