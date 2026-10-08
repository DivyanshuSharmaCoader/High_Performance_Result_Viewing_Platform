import { Section, Switch, toast } from "@scorecode/ui";

import { toastError } from "../../lib/forms";
import { usePreferences, useSetPreferences } from "./api";

/** Optional email only: sign-in and password emails always go, whatever this says. */
export function NotificationPreferences() {
  const prefs = usePreferences();
  const save = useSetPreferences();
  if (!prefs.data) return null;
  return (
    <Section title="Notifications">
      <Switch
        checked={prefs.data.email_results}
        disabled={save.isPending}
        label="Email me when new results are published"
        description="You'll always see new results here, and emails about signing in or resetting your password still arrive. Emails never contain marks."
        onCheckedChange={(email_results) =>
          save.mutate(
            { email_results },
            {
              onSuccess: () =>
                toast.success(email_results ? "We'll email you about new results" : "No more result emails"),
              onError: toastError,
            },
          )
        }
      />
    </Section>
  );
}
