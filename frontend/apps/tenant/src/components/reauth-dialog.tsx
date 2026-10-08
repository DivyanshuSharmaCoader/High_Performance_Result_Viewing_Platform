import { api, ApiError } from "@scorecode/api-client";
import { Button, Callout, Dialog, DialogContent, Field, Input, PasswordInput } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { meKey } from "../lib/session";

/** The password prompt itself, loaded only when an action actually needs it (students rarely do). */
export default function ReauthDialog({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const qc = useQueryClient();
  const confirm = useMutation({
    mutationFn: () =>
      api.post("/api/v1/auth/reauth", needsCode ? { password, totp_code: code } : { password }),
    onError: (e) => {
      if (e instanceof ApiError && e.code === "totp-required") setNeedsCode(true);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: meKey });
      onDone();
    },
  });
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent
        title="Confirm it's you"
        description="For your security, enter your password to continue with this action."
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              form="reauth-form"
              type="submit"
              loading={confirm.isPending}
              disabled={!password || (needsCode && code.trim().length < 6)}
            >
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
          {confirm.error &&
            !(confirm.error instanceof ApiError && confirm.error.code === "totp-required" && !code) && (
              <Callout tone="danger">
                {needsCode ? "The password or the code isn't right." : "That password isn't right."}
              </Callout>
            )}
          <Field label="Password">
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              autoFocus={!needsCode}
            />
          </Field>
          {needsCode && (
            <Field label="Authenticator code" description="Or one of your recovery codes.">
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={20}
                autoFocus
              />
            </Field>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}
