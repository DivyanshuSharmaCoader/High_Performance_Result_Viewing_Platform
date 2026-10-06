import { api, type ActivationCodes } from "@scorecode/api-client";
import {
  Button,
  Callout,
  Checkbox,
  EmptyState,
  Field,
  PageHeader,
  Section,
  Select,
  StatTile,
  formatNumber,
  noun,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { KeyRound, Network } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { toastError } from "../../lib/forms";
import { useCurrentCohorts, useInvalidateStudents, useStudentTotal } from "./api";
import { CodesTable, PrintableSlips, SlipsActions, SlipsSummary } from "./slips";

export default function ActivationPage() {
  const { cohorts, session, isPending } = useCurrentCohorts();
  const [cohortId, setCohortId] = useState("");
  const [replace, setReplace] = useState(false);
  const [result, setResult] = useState<ActivationCodes | null>(null);
  const invalidate = useInvalidateStudents();
  const selected = cohortId || cohorts[0]?.id || "";
  const cohort = cohorts.find((c) => c.id === selected);
  const total = useStudentTotal({ cohortId: selected }, Boolean(selected));
  const none = useStudentTotal({ cohortId: selected, account: "none" }, Boolean(selected));
  const pending = useStudentTotal({ cohortId: selected, account: "pending" }, Boolean(selected));
  const active = useStudentTotal({ cohortId: selected, account: "active" }, Boolean(selected));
  const willIssue = (none.data ?? 0) + (replace ? (pending.data ?? 0) : 0);

  const issue = useMutation({
    mutationFn: () =>
      api.post<ActivationCodes>("/api/v1/admin/activation-codes", {
        cohort_id: selected,
        replace_existing: replace,
      }),
    onSuccess: (r) => {
      invalidate();
      setResult(r);
      if (r.issued.length === 0) toast.info("No new codes were needed for this cohort.");
    },
    onError: (e) => toastError(e),
  });

  if (!isPending && cohorts.length === 0) {
    return (
      <>
        <PageHeader title="Activation codes" />
        <EmptyState
          icon={<Network />}
          title="Set up cohorts first"
          description="Codes are printed per cohort. Create a session and its cohorts, then add students to them."
          action={
            <Button asChild>
              <Link to="/admin/academics">Go to academic structure</Link>
            </Button>
          }
        />
      </>
    );
  }

  if (result && result.issued.length > 0) {
    return (
      <>
        <PageHeader
          breadcrumb={<Link to="/admin/students">Students</Link>}
          title={`${formatNumber(result.issued.length)} activation ${noun(result.issued.length, "code")} for ${result.cohort_code ?? "students"}`}
          description="Hand each student their slip. They enter their enrollment number and code once, then choose a password."
          actions={
            <SlipsActions
              result={result}
              fileName={`activation-codes-${result.cohort_code ?? "students"}.csv`}
            />
          }
        />
        <div className="flex flex-col gap-4">
          <Callout tone="warning" title="These codes are shown only now">
            ScoreCode keeps only a fingerprint of each code, so they can&apos;t be displayed again. Print the
            slips or download the CSV before leaving this page. Lost a slip? Issue a replacement from the
            student&apos;s page.
          </Callout>
          <SlipsSummary result={result} />
          <CodesTable codes={result.issued} />
          <div>
            <Button variant="secondary" onClick={() => setResult(null)}>
              Done — choose another cohort
            </Button>
          </div>
        </div>
        <PrintableSlips codes={result.issued} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/admin/students">Students</Link>}
        title="Activation codes"
        description="Students activate their portal account with a one-time code. Generate codes for a cohort and print one slip per student."
      />
      <Section>
        <div className="flex flex-col gap-6">
          <Field label="Cohort" description={session ? `Cohorts in ${session.name}.` : undefined}>
            <Select
              value={selected}
              onChange={(e) => {
                setCohortId(e.target.value);
                setResult(null);
              }}
              className="sm:w-96"
            >
              {cohorts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-4">
            <StatTile label="Students" value={total.isPending ? "…" : formatNumber(total.data)} />
            <StatTile label="No account yet" value={none.isPending ? "…" : formatNumber(none.data)} />
            <StatTile
              label="Code issued, unused"
              value={pending.isPending ? "…" : formatNumber(pending.data)}
            />
            <StatTile label="Activated" value={active.isPending ? "…" : formatNumber(active.data)} />
          </div>
          <Checkbox
            checked={replace}
            onCheckedChange={setReplace}
            label="Also replace unused codes"
            description="Old slips for those students stop working. Use this if slips were lost or never handed out."
          />
          <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
            <Button
              leadingIcon={<KeyRound />}
              disabled={!cohort || willIssue === 0}
              loading={issue.isPending}
              onClick={() => issue.mutate()}
            >
              {willIssue > 0
                ? `Generate ${formatNumber(willIssue)} ${noun(willIssue, "code")}`
                : "Everyone in this cohort has a code"}
            </Button>
            {result && result.issued.length === 0 && <SlipsSummary result={result} />}
          </div>
        </div>
      </Section>
    </>
  );
}
