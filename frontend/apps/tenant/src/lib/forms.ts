import { ApiError, splitProblem } from "@scorecode/api-client";
import { toast } from "@scorecode/ui";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

/**
 * Show a server error where it belongs: on the matching field when the server names one, otherwise
 * as a toast. Returns the message shown at form level (or null when every error was placed on a field).
 */
export function applyServerError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): string | null {
  const { fields: placed, formMessage } = splitProblem(error, fields);
  for (const [field, message] of Object.entries(placed))
    setError(field as Path<T>, { type: "server", message });
  return formMessage;
}

export function toastError(error: unknown, fallback = "Something went wrong. Please try again."): void {
  if (error instanceof ApiError) {
    // A plan limit or a feature outside the plan: say so, and offer the way forward.
    const plan = error.status === 402 || error.code === "feature-not-in-plan";
    toast.error(error.title !== error.detail ? error.title : fallback, {
      description: error.detail,
      action: plan
        ? {
            label: "See plans",
            onClick: () => void import("../routes").then((m) => m.router.navigate("/admin/plan")),
          }
        : undefined,
    });
    return;
  }
  toast.error(fallback);
}
