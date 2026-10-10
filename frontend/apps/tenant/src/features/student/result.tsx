import { ApiError } from "@scorecode/api-client";
import { Button, Callout, Skeleton } from "@scorecode/ui";
import { ArrowLeft, Printer } from "lucide-react";
import { Link, useParams } from "react-router";

import { useI18n } from "../../lib/i18n";
import { useMyResult, useMyStats } from "./api";
import { ClassStats, type FullStats } from "./class-stats";
import { MarksheetCard } from "./marksheet";
import { StudentResultView } from "./result-view";

export default function StudentResultPage() {
  const { publicationId = "" } = useParams();
  const { t, dateTime } = useI18n();
  const q = useMyResult(publicationId);
  const stats = useMyStats(publicationId);
  const averages = Object.fromEntries(
    ((stats.data?.stats?.papers ?? []) as { course_code: string; average: string | null }[]).map((p) => [
      p.course_code,
      p.average,
    ]),
  );
  const classAverage = (stats.data?.stats?.average_percentage ?? null) as string | null;
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3 print:hidden">
        <Link to="/me" className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
          <ArrowLeft className="size-4" aria-hidden /> {t("result.my_results")}
        </Link>
        {q.data && (
          <Button size="sm" variant="ghost" leadingIcon={<Printer />} onClick={() => window.print()}>
            {t("result.print")}
          </Button>
        )}
      </div>
      {q.isPending ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-48 w-full rounded-2xl" />
          <Skeleton className="h-36 w-full rounded-xl" />
        </div>
      ) : q.error ? (
        <Callout tone="danger">
          {q.error instanceof ApiError && q.error.status === 404
            ? t("result.not_available")
            : t("result.load_failed")}
        </Callout>
      ) : (
        <>
          {q.data.revised && (
            <Callout tone="info" className="mb-4">
              {t("result.revised_notice", { date: dateTime(q.data.published_at) })}
            </Callout>
          )}
          <StudentResultView payload={q.data.payload} averages={averages} />
          <MarksheetCard publicationId={publicationId} />
          {stats.data?.stats?.histogram ? (
            <ClassStats stats={stats.data.stats as FullStats} percentage={q.data.payload.result.percentage} />
          ) : null}
          <p className="mt-5 text-[12px] text-fg-subtle">
            {t("result.published_by", {
              institution: q.data.payload.institution.name,
              date: dateTime(q.data.published_at),
            })}
            {classAverage && <> · {t("result.class_average_pct", { value: classAverage })}</>}.
          </p>
        </>
      )}
    </>
  );
}
