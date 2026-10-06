import { splitProblem } from "@scorecode/api-client";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): string | null {
  const { fields: placed, formMessage } = splitProblem(error, fields);
  for (const [field, message] of Object.entries(placed))
    setError(field as Path<T>, { type: "server", message });
  return formMessage;
}
