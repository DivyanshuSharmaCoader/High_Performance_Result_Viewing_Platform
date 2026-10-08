import { ApiError } from "@scorecode/api-client";
import { Button, Callout, Skeleton, formatDateTime } from "@scorecode/ui";
import { ArrowLeft, Printer } from "lucide-react";
import { Link, useParams } from "react-router";

import { useMyResult, useMyStats } from "./api";
import { MarksheetCard } from "./marksheet";
import { StudentResultView } from "./result-view";

export default function StudentResultPage() {
  const { publicationId = "" } = useParams();
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
          <ArrowLeft className="size-4" aria-hidden /> My results
        </Link>
        {q.data && (
          <Button size="sm" variant="ghost" leadingIcon={<Printer />} onClick={() => window.print()}>
            Print
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
            ? "This result isn't available. It may have been withdrawn by your institution."
            : "Your result couldn't be loaded. Check your connection and try again."}
        </Callout>
      ) : (
        <>
          {q.data.revised && (
            <Callout tone="info" className="mb-4">
              This is a revised result, published {formatDateTime(q.data.published_at)}. It replaces the
              earlier version.
            </Callout>
          )}
          <StudentResultView payload={q.data.payload} averages={averages} />
          <MarksheetCard publicationId={publicationId} />
          <p className="mt-5 text-[12px] text-fg-subtle">
            Published by {q.data.payload.institution.name} on {formatDateTime(q.data.published_at)}
            {classAverage && <> · class average {classAverage}%</>}.
          </p>
        </>
      )}
    </>
  );
}
