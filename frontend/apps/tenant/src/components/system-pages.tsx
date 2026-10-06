import { isApiError } from "@scorecode/api-client";
import { Button, Skeleton, buttonClasses } from "@scorecode/ui";
import { Compass, Lock, RefreshCw, SearchX, ServerCrash, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { Link, isRouteErrorResponse, useRouteError } from "react-router";

function Centered({
  icon,
  title,
  children,
  action,
  tone = "neutral",
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "warning";
}) {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-16">
      <div className="w-full max-w-md text-center animate-slide-up">
        <div
          className={
            "mx-auto mb-5 flex size-12 items-center justify-center rounded-2xl border shadow-xs [&_svg]:size-6 " +
            (tone === "warning"
              ? "border-warning-border bg-warning-soft text-warning"
              : "border-border bg-surface text-fg-subtle")
          }
        >
          {icon}
        </div>
        <h1 className="text-xl font-semibold tracking-[-0.01em] text-fg">{title}</h1>
        <div className="mt-2 text-sm leading-6 text-fg-subtle">{children}</div>
        {action && <div className="mt-6 flex justify-center gap-2">{action}</div>}
      </div>
    </main>
  );
}

/** Shown while the institution's configuration loads (skeleton, not a spinner). */
export function BootSplash() {
  return (
    <div className="flex min-h-dvh items-center justify-center" aria-busy="true" aria-label="Loading">
      <div className="flex w-64 flex-col items-center gap-4">
        <Skeleton className="size-12 rounded-xl" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-3 w-32" />
      </div>
    </div>
  );
}

function exampleHost(): string {
  const parts = window.location.hostname.split(".");
  return ["yourschool", ...parts.slice(1)].join(".");
}

export function NoInstitution() {
  return (
    <Centered icon={<SearchX />} title="There's no institution here">
      Check the address you were given. Each institution has its own portal address, like{" "}
      <span className="font-medium text-fg">{exampleHost()}</span>.
    </Centered>
  );
}

export function PortalUnavailable({ institution }: { institution?: string | undefined }) {
  return (
    <Centered icon={<Wrench />} title="Portal temporarily unavailable" tone="warning">
      {institution ? <span className="font-medium text-fg">{institution}</span> : "This institution"}'s
      results portal is unavailable right now. Your results are safe — please check back later or contact your
      institution.
    </Centered>
  );
}

export function BootError({ onRetry }: { onRetry: () => void }) {
  return (
    <Centered
      icon={<ServerCrash />}
      title="We couldn't load the portal"
      action={
        <Button onClick={onRetry} leadingIcon={<RefreshCw />}>
          Try again
        </Button>
      }
    >
      This is usually a brief network problem. Your data is safe.
    </Centered>
  );
}

export function Forbidden() {
  return (
    <Centered
      icon={<Lock />}
      title="You don't have access to this page"
      action={
        <Link to="/" className={buttonClasses("secondary")}>
          Go to your home page
        </Link>
      }
    >
      Ask an administrator at your institution if you think you should.
    </Centered>
  );
}

export function NotFound() {
  return (
    <Centered
      icon={<Compass />}
      title="Page not found"
      action={
        <Link to="/" className={buttonClasses("secondary")}>
          Go home
        </Link>
      }
    >
      The page you're looking for doesn't exist or was moved.
    </Centered>
  );
}

export function RouteError() {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFound />;
  const requestId = isApiError(error) ? error.requestId : undefined;
  return (
    <Centered
      icon={<ServerCrash />}
      title="Something went wrong"
      action={
        <Button onClick={() => window.location.reload()} leadingIcon={<RefreshCw />}>
          Reload page
        </Button>
      }
    >
      An unexpected error occurred. If it keeps happening, contact support
      {requestId ? (
        <>
          {" "}
          and mention reference{" "}
          <code className="rounded bg-surface-2 px-1 font-mono text-xs text-fg">{requestId}</code>
        </>
      ) : null}
      .
    </Centered>
  );
}

/** Shell-shaped skeleton shown while the session loads. */
export function AppSkeleton() {
  return (
    <div className="flex min-h-dvh" aria-busy="true" aria-label="Loading">
      <div className="hidden w-[248px] shrink-0 flex-col gap-3 border-r border-border bg-surface p-4 lg:flex">
        <Skeleton className="h-9 w-40" />
        <div className="mt-4 flex flex-col gap-2">
          {Array.from({ length: 7 }, (_, i) => (
            <Skeleton key={i} className="h-7" />
          ))}
        </div>
      </div>
      <div className="flex-1 p-6 lg:p-10">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="mt-3 h-4 w-96 max-w-full" />
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="mt-6 h-64 rounded-xl" />
      </div>
    </div>
  );
}
