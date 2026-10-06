import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

const styles = {
  info: { box: "bg-info-soft border-info-border", icon: <Info className="text-info" />, title: "text-info" },
  success: {
    box: "bg-success-soft border-success-border",
    icon: <CheckCircle2 className="text-success" />,
    title: "text-success",
  },
  warning: {
    box: "bg-warning-soft border-warning-border",
    icon: <AlertTriangle className="text-warning" />,
    title: "text-warning",
  },
  danger: {
    box: "bg-danger-soft border-danger-border",
    icon: <XCircle className="text-danger" />,
    title: "text-danger",
  },
} as const;

export interface CalloutProps {
  tone?: keyof typeof styles;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function Callout({ tone = "info", title, children, action, className }: CalloutProps) {
  const s = styles[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex gap-3 rounded-lg border px-4 py-3 text-sm [&>svg]:mt-0.5 [&>svg]:size-[18px] [&>svg]:shrink-0",
        s.box,
        className,
      )}
    >
      {s.icon}
      <div className="min-w-0 flex-1">
        {title && <p className={cn("font-semibold", s.title)}>{title}</p>}
        {children && <div className={cn("leading-6 text-fg-muted", title && "mt-0.5")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
