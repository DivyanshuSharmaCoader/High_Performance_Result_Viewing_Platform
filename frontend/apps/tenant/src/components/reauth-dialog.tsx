import { api } from "@scorecode/api-client";
import { Button, Callout, Dialog, DialogContent, Field, PasswordInput } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { meKey } from "../lib/session";

/** The password prompt itself, loaded only when an action actually needs it (students rarely do). */
export default function ReauthDialog({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [password, setPassword] = useState("");
  const qc = useQueryClient();
  const confirm = useMutation({
    mutationFn: () => api.post("/api/v1/auth/reauth", { password }),
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
  );
}
