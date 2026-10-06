import { api, ApiError } from "@scorecode/api-client";
import { Button, Callout, Dialog, DialogContent, Field } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

import { meKey } from "../lib/session";
import { PasswordInput } from "./password-input";

type Run = <T>(action: () => Promise<T>) => Promise<T>;
const ReauthContext = createContext<Run | null>(null);

/**
 * Sensitive actions (role changes, ownership transfer, publishing) need a recent password confirmation
 * (docs/10 §2). `withReauth(action)` runs the action; if the server answers `reauth-required`, it asks
 * for the password once and retries the same action.
 */
export function ReauthProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const pending = useRef<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);
  const qc = useQueryClient();
  const confirm = useMutation({
    mutationFn: () => api.post("/api/v1/auth/reauth", { password }),
    onSuccess: () => {
      setOpen(false);
      setPassword("");
      void qc.invalidateQueries({ queryKey: meKey });
      pending.current?.resolve();
      pending.current = null;
    },
  });

  const run = useCallback<Run>(async (action) => {
    try {
      return await action();
    } catch (error) {
      if (!(error instanceof ApiError && error.code === "reauth-required")) throw error;
      await new Promise<void>((resolve, reject) => {
        pending.current = { resolve, reject };
        setOpen(true);
      });
      return action();
    }
  }, []);

  return (
    <ReauthContext.Provider value={run}>
      {children}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) {
            pending.current?.reject(
              new ApiError(401, { code: "reauth-cancelled", detail: "Action cancelled." }),
            );
            pending.current = null;
            setPassword("");
            confirm.reset();
          }
          setOpen(next);
        }}
      >
        <DialogContent
          title="Confirm it's you"
          description="For your security, enter your password to continue with this action."
          size="sm"
          footer={
            <>
              <Button variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button form="reauth-form" type="submit" loading={confirm.isPending} disabled={!password}>
                Confirm
              </Button>
            </>
          }
        >
          <form
            id="reauth-form"
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              confirm.mutate();
            }}
          >
            {confirm.error && <Callout tone="danger">That password isn't right.</Callout>}
            <Field label="Password">
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
              />
            </Field>
          </form>
        </DialogContent>
      </Dialog>
    </ReauthContext.Provider>
  );
}

export function useReauth(): Run {
  const ctx = useContext(ReauthContext);
  if (!ctx) throw new Error("useReauth must be used inside ReauthProvider");
  return ctx;
}
