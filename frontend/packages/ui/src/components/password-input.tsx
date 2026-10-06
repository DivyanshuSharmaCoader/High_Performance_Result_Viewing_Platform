import { cn } from "../lib/cn";
import { Input } from "./input";
import { Eye, EyeOff } from "lucide-react";
import { forwardRef, useState, type InputHTMLAttributes } from "react";

export const PasswordInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function PasswordInput(props, ref) {
    const [visible, setVisible] = useState(false);
    return (
      <Input
        ref={ref}
        type={visible ? "text" : "password"}
        {...props}
        trailing={
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="rounded p-1.5 text-fg-subtle hover:bg-surface-2 hover:text-fg"
            aria-label={visible ? "Hide password" : "Show password"}
            aria-pressed={visible}
          >
            {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        }
      />
    );
  },
);

/** Lightweight guidance matching the server's rules (length first, NIST 800-63B style). */
export function PasswordStrength({ value, minLength }: { value: string; minLength: number }) {
  if (!value) return null;
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(value)).length;
  const score =
    value.length < minLength ? 0 : value.length >= minLength + 6 || variety >= 3 ? 3 : variety >= 2 ? 2 : 1;
  const labels = ["Too short", "Okay", "Good", "Strong"];
  const colors = ["bg-danger-solid", "bg-warning", "bg-brand", "bg-success"];
  return (
    <div className="mt-2" aria-live="polite">
      <div className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn("h-1 flex-1 rounded-full", i < Math.max(1, score) ? colors[score] : "bg-surface-3")}
          />
        ))}
      </div>
      <p className="mt-1.5 text-xs text-fg-subtle">
        {labels[score]}
        {value.length < minLength
          ? ` — use at least ${minLength} characters.`
          : ". Longer passphrases are easiest to remember and hardest to guess."}
      </p>
    </div>
  );
}
