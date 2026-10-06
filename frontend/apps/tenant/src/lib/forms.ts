import { ApiError } from "@scorecode/api-client";
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
  if (!(error instanceof ApiError)) {
    return "Something went wrong. Please try again.";
  }
  const placed = Object.entries(error.fieldErrors()).filter(([f]) => fields.includes(f));
  for (const [field, message] of placed) setError(field as Path<T>, { type: "server", message });
  if (placed.length > 0) return null;
  return error.detail;
}

export function toastError(error: unknown, fallback = "Something went wrong. Please try again."): void {
  if (error instanceof ApiError) {
    toast.error(error.title !== error.detail ? error.title : fallback, { description: error.detail });
    return;
  }
  toast.error(fallback);
}
