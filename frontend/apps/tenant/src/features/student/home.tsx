import { EmptyState } from "@scorecode/ui";
import { FileText } from "lucide-react";

import { useSession } from "../../lib/session";
import { useTenant } from "../../lib/tenant";

export default function StudentHome() {
  const me = useSession();
  const { branding } = useTenant();
  const first = me.full_name.split(" ")[0] ?? me.full_name;
  return (
    <>
      <h1 className="text-[22px] font-semibold tracking-[-0.01em] text-fg">Hello, {first}</h1>
      <p className="mt-1 text-sm text-fg-subtle">
        Enrollment no. <span className="font-mono text-fg-muted">{me.login_id}</span>
      </p>
      <div className="mt-6 rounded-xl border border-border bg-surface">
        <EmptyState
          icon={<FileText />}
          title="No results yet"
          description={`Your results will appear here as soon as ${branding.short_name ?? branding.display_name} publishes them.`}
        />
      </div>
    </>
  );
}
