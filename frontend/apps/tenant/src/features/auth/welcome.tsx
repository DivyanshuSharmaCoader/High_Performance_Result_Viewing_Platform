import { api } from "@scorecode/api-client";
import { Callout, Skeleton, toast } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { AuthLayout } from "../../components/auth-layout";
import { meKey } from "../../lib/session";

/** Landing page after self-serve sign-up: exchanges the one-time handoff token for a session. */
export default function WelcomePage() {
  const [params] = useSearchParams();
  const token = params.get("handoff") ?? "";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const started = useRef(false);
  const handoff = useMutation({
    mutationFn: () => api.post("/api/v1/auth/handoff", { token }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: meKey });
      toast.success("Your portal is ready", { description: "Let's finish setting up your institution." });
      void navigate("/admin", { replace: true });
    },
  });
  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      handoff.mutate();
    }
  }, [token, handoff]);

  return (
    <AuthLayout title={handoff.isError || !token ? "Sign in to continue" : "Setting up your portal…"}>
      {handoff.isError || !token ? (
        <Callout tone="info" title="This sign-in link has expired">
          Your portal was created.{" "}
          <Link to="/login" className="font-medium text-brand-ink hover:underline">
            Sign in
          </Link>{" "}
          with the email and password you chose.
        </Callout>
      ) : (
        <div className="flex flex-col gap-3" aria-busy="true">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      )}
    </AuthLayout>
  );
}
