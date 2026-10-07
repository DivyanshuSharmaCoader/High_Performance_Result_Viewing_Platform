import { ApiError } from "@scorecode/api-client";
import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

type Run = <T>(action: () => Promise<T>) => Promise<T>;
const ReauthContext = createContext<Run | null>(null);
const ReauthDialog = lazy(() => import("./reauth-dialog"));

/**
 * Sensitive actions (role changes, ownership transfer, publishing) need a recent password confirmation
 * (docs/10 §2). `withReauth(action)` runs the action; if the server answers `reauth-required`, it asks
 * for the password once and retries the same action.
 */
export function ReauthProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const pending = useRef<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);

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

  const finish = (confirmed: boolean) => {
    setOpen(false);
    if (confirmed) pending.current?.resolve();
    else
      pending.current?.reject(new ApiError(401, { code: "reauth-cancelled", detail: "Action cancelled." }));
    pending.current = null;
  };

  return (
    <ReauthContext.Provider value={run}>
      {children}
      {open && (
        <Suspense fallback={null}>
          <ReauthDialog onDone={() => finish(true)} onCancel={() => finish(false)} />
        </Suspense>
      )}
    </ReauthContext.Provider>
  );
}

export function useReauth(): Run {
  const ctx = useContext(ReauthContext);
  if (!ctx) throw new Error("useReauth must be used inside ReauthProvider");
  return ctx;
}
