import { FileUp } from "lucide-react";
import { useRef, useState, type DragEvent, type ReactNode } from "react";

import { cn } from "../lib/cn";

export function FileDropzone({
  accept,
  onFile,
  hint,
  disabled,
  maxBytes,
  children,
}: {
  accept: string;
  onFile: (file: File) => void;
  hint?: ReactNode;
  disabled?: boolean;
  maxBytes?: number;
  children?: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const take = (file: File | undefined) => {
    if (!file) return;
    if (maxBytes && file.size > maxBytes) {
      setError(
        `That file is ${(file.size / 1024 / 1024).toFixed(1)} MB; the limit is ${Math.round(maxBytes / 1024 / 1024)} MB.`,
      );
      return;
    }
    setError(null);
    onFile(file);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (!disabled) take(e.dataTransfer.files[0]);
  };
  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          dragging
            ? "border-brand bg-brand-soft"
            : "border-border-strong bg-surface hover:border-fg-disabled hover:bg-surface-2/50",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <span className="flex size-10 items-center justify-center rounded-full bg-brand-soft text-brand-ink">
          <FileUp className="size-5" aria-hidden />
        </span>
        {children ?? (
          <span className="text-sm">
            <span className="font-semibold text-brand-ink">Choose a file</span>
            <span className="text-fg-muted"> or drag it here</span>
          </span>
        )}
        {hint && <span className="text-[13px] text-fg-subtle">{hint}</span>}
      </button>
      {/* The button above is the control people and screen readers use; this input only opens the
          file picker, so it is hidden from the accessibility tree (axe: no unlabelled duplicate). */}
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        onChange={(e) => {
          take(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {error && (
        <p role="alert" className="mt-2 text-[13px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
