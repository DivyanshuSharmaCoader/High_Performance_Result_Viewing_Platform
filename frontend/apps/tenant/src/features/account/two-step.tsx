import { api, ApiError } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  Checkbox,
  Dialog,
  DialogContent,
  Field,
  Input,
  Section,
  formatDateTime,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, KeyRound, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useReauth } from "../../components/reauth";
import { toastError } from "../../lib/forms";
import { meKey } from "../../lib/session";

interface MfaStatus {
  enabled: boolean;
  enabled_at: string | null;
  recovery_codes_left: number;
}
interface Setup {
  secret: string;
  uri: string;
  qr_svg: string;
}

const statusKey = ["me", "mfa"] as const;
const group = (secret: string) => secret.replace(/(.{4})/g, "$1 ").trim();

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = `ScoreCode recovery codes (each works once)\n\n${codes.join("\n")}\n`;
  return (
    <div className="flex flex-col gap-4">
      <Callout tone="warning" title="Save these now — they won't be shown again">
        If you lose your phone, a recovery code signs you in instead of the app. Keep them somewhere safe,
        like a password manager.
      </Callout>
      <ol
        className="grid grid-cols-2 gap-2 rounded-lg bg-surface-2 p-3 font-mono text-[13px]"
        aria-label="Recovery codes"
      >
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          leadingIcon={copied ? <Check /> : <Copy />}
          onClick={() =>
            void navigator.clipboard.writeText(text).then(
              () => setCopied(true),
              () => toast.error("Couldn't copy. Select the codes and copy them yourself."),
            )
          }
        >
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          leadingIcon={<Download />}
          onClick={() => {
            const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
            const a = document.createElement("a");
            a.href = url;
            a.download = "scorecode-recovery-codes.txt";
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Download .txt
        </Button>
      </div>
      <Checkbox checked={saved} onCheckedChange={setSaved} label="I've saved my recovery codes" />
      <Button disabled={!saved} onClick={onDone}>
        Done
      </Button>
    </div>
  );
}

/** Ask for a code, then run an action that needs one (turn off, new recovery codes). */
function CodeDialog({
  title,
  description,
  confirmLabel,
  danger,
  onConfirm,
  onClose,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: (code: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        title={title}
        description={description}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              form="mfa-code"
              type="submit"
              variant={danger ? "danger" : "primary"}
              loading={busy}
              disabled={code.trim().length < 6}
            >
              {confirmLabel}
            </Button>
          </>
        }
      >
        <form
          id="mfa-code"
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            onConfirm(code)
              .catch((err: unknown) => {
                setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
                setCode("");
              })
              .finally(() => setBusy(false));
          }}
        >
          {error && <Callout tone="danger">{error}</Callout>}
          <Field label="Authenticator or recovery code">
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoComplete="one-time-code"
              maxLength={20}
              autoFocus
            />
          </Field>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Two-step sign-in for staff (P15.5): an authenticator app, plus recovery codes for a lost phone. */
export function TwoStepSection() {
  const qc = useQueryClient();
  const withReauth = useReauth();
  const status = useQuery({ queryKey: statusKey, queryFn: () => api.get<MfaStatus>("/api/v1/me/mfa") });
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [asking, setAsking] = useState<null | "off" | "codes">(null);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: statusKey });
    void qc.invalidateQueries({ queryKey: meKey });
  };
  const begin = useMutation({
    mutationFn: () => withReauth(() => api.post<Setup>("/api/v1/me/mfa/setup")),
    onSuccess: (s) => {
      setCode("");
      setSetup(s);
    },
    onError: (e) => {
      if (!(e instanceof ApiError && e.code === "reauth-cancelled")) toastError(e);
    },
  });
  const enable = useMutation({
    mutationFn: () => api.post<{ recovery_codes: string[] }>("/api/v1/me/mfa/enable", { code }),
    onSuccess: (r) => {
      setSetup(null);
      setCodes(r.recovery_codes);
      refresh();
    },
  });
  if (!status.data) return null;
  const s = status.data;
  return (
    <Section
      title="Two-step sign-in"
      description="Sign-ins need a code from your phone as well as your password, so a leaked password alone can't get in."
      actions={
        s.enabled ? (
          <Badge tone="success" dot>
            On
          </Badge>
        ) : (
          <Badge tone="warning" dot>
            Off
          </Badge>
        )
      }
    >
      {s.enabled ? (
        <div className="flex flex-col gap-3">
          <p className="flex items-center gap-2 text-sm text-fg-muted">
            <ShieldCheck className="size-4 text-success" aria-hidden />
            On since {formatDateTime(s.enabled_at)} · {s.recovery_codes_left} recovery code
            {s.recovery_codes_left === 1 ? "" : "s"} left
          </p>
          {s.recovery_codes_left <= 3 && (
            <Callout tone="warning">
              You're running low on recovery codes. Make new ones while you still have your phone.
            </Callout>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="secondary"
              leadingIcon={<KeyRound />}
              onClick={() => setAsking("codes")}
            >
              New recovery codes
            </Button>
            <Button size="sm" variant="danger-outline" onClick={() => setAsking("off")}>
              Turn off
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-fg-muted">
            Use any authenticator app — Google Authenticator, Microsoft Authenticator, 1Password or Authy.
          </p>
          <Button leadingIcon={<ShieldCheck />} loading={begin.isPending} onClick={() => begin.mutate()}>
            Set up two-step sign-in
          </Button>
        </div>
      )}

      <Dialog open={setup !== null} onOpenChange={(v) => !v && setSetup(null)}>
        <DialogContent
          title="Set up two-step sign-in"
          description="Scan the code with your authenticator app, then enter the 6-digit code it shows."
          footer={
            <>
              <Button variant="secondary" onClick={() => setSetup(null)}>
                Cancel
              </Button>
              <Button
                form="mfa-enable"
                type="submit"
                loading={enable.isPending}
                disabled={code.trim().length !== 6}
              >
                Turn on
              </Button>
            </>
          }
        >
          {setup && (
            <form
              id="mfa-enable"
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                enable.mutate();
              }}
            >
              <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
                <img
                  src={setup.qr_svg}
                  alt="QR code for your authenticator app"
                  className="size-40 rounded-lg bg-white p-2"
                />
                <div className="min-w-0 text-[13px] text-fg-muted">
                  <p>Can't scan? Choose “enter a setup key” in the app and type:</p>
                  <p className="mt-1 break-all font-mono text-sm font-medium text-fg">
                    {group(setup.secret)}
                  </p>
                </div>
              </div>
              {enable.error && (
                <Callout tone="danger">
                  {enable.error instanceof ApiError ? enable.error.detail : "That didn't work. Try again."}
                </Callout>
              )}
              <Field label="Code from the app">
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="123456"
                  autoFocus
                />
              </Field>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={codes !== null} onOpenChange={() => undefined}>
        <DialogContent title="Two-step sign-in is on" description="One last thing: your recovery codes.">
          {codes && <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />}
        </DialogContent>
      </Dialog>

      {asking === "off" && (
        <CodeDialog
          title="Turn off two-step sign-in?"
          description="Sign-ins will need only your password again."
          confirmLabel="Turn off"
          danger
          onClose={() => setAsking(null)}
          onConfirm={async (c) => {
            await api.post("/api/v1/me/mfa/disable", { code: c });
            setAsking(null);
            refresh();
            toast.success("Two-step sign-in is off");
          }}
        />
      )}
      {asking === "codes" && (
        <CodeDialog
          title="Make new recovery codes"
          description="Your old codes stop working. Enter a code from your authenticator app."
          confirmLabel="Make new codes"
          onClose={() => setAsking(null)}
          onConfirm={async (c) => {
            const r = await api.post<{ recovery_codes: string[] }>("/api/v1/me/mfa/recovery-codes", {
              code: c,
            });
            setAsking(null);
            setCodes(r.recovery_codes);
            refresh();
          }}
        />
      )}
    </Section>
  );
}
