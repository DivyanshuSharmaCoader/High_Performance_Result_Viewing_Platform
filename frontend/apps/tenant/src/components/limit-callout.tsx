import { ApiError } from "@scorecode/api-client";
import { Callout } from "@scorecode/ui";
import { Link } from "react-router";

/** Explains a plan limit or missing feature (HTTP 402) with the way forward. */
export function PlanLimitCallout({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || error.status !== 402) return null;
  return (
    <Callout
      tone="warning"
      title={error.code === "limit-exceeded" ? "Plan limit reached" : "Not included in your plan"}
      action={
        <Link to="/admin/plan" className="text-[13px] font-medium text-brand-ink hover:underline">
          View plan
        </Link>
      }
    >
      {error.detail}
    </Callout>
  );
}
