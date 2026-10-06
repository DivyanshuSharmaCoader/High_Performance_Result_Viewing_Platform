import { api, ApiError } from "@scorecode/api-client";
import { Callout, Skeleton } from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router";

interface Verified {
  slug: string;
  tenant_url: string;
  handoff_url: string;
}

/** Email confirmation link target: creates the tenant, then hands the owner off to their new portal. */
export default function VerifyPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const started = useRef(false);
  const verify = useMutation({
    mutationFn: () => api.post<Verified>("/api/v1/signup/verify", { token }),
    onSuccess: (data) => {
      window.setTimeout(() => window.location.assign(data.handoff_url), 1200);
    },
  });
  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      verify.mutate();
    }
  }, [token, verify]);

  return (
    <div className="mx-auto max-w-md px-5 py-24 text-center">
      {verify.isSuccess ? (
        <div className="animate-slide-up">
          <CheckCircle2 className="mx-auto size-12 text-success" aria-hidden />
          <h1 className="mt-5 text-2xl font-semibold tracking-[-0.02em]">Your portal is ready</h1>
          <p className="mt-3 text-[15px] text-fg-muted">
            Taking you to <span className="font-medium text-fg">{new URL(verify.data.tenant_url).host}</span>…
          </p>
          <p className="mt-6 text-[13px] text-fg-subtle">
            Not redirected?{" "}
            <a href={verify.data.handoff_url} className="font-medium text-brand-ink hover:underline">
              Continue
            </a>
          </p>
        </div>
      ) : verify.isError || !token ? (
        <Callout tone="danger" title="We couldn't confirm your email">
          {verify.error instanceof ApiError ? verify.error.detail : "This link is incomplete."}{" "}
          <Link to="/signup" className="font-medium text-brand-ink hover:underline">
            Sign up again
          </Link>
        </Callout>
      ) : (
        <div className="flex flex-col items-center gap-3" aria-busy="true">
          <Skeleton className="size-12 rounded-full" />
          <Skeleton className="h-5 w-56" />
          <p className="text-sm text-fg-subtle">Creating your portal…</p>
        </div>
      )}
    </div>
  );
}
