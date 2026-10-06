import { api, ApiError, type BrandingOut } from "@scorecode/api-client";
import {
  Button,
  Callout,
  ConfirmDialog,
  Field,
  FileDropzone,
  Input,
  Section,
  Select,
  SettingRow,
  Skeleton,
  Switch,
  TenantMark,
  Textarea,
  applyBrandTokens,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import { PlanLimitCallout } from "../../components/limit-callout";
import { toastError } from "../../lib/forms";
import { tenantConfigKey, useTenant } from "../../lib/tenant";

const FONTS = ["Inter", "Source Sans 3", "Noto Sans", "IBM Plex Sans", "Merriweather Sans"];
const HEX = /^#[0-9a-f]{6}$/i;

function luminance(hex: string): number {
  const c = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * (c[0] ?? 0) + 0.7152 * (c[1] ?? 0) + 0.0722 * (c[2] ?? 0);
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}
function readableOn(bg: string): string {
  return contrast(bg, "#ffffff") >= contrast(bg, "#111827") ? "#ffffff" : "#111827";
}
function colorError(value: string): string | undefined {
  if (!HEX.test(value)) return "Use a 6-digit hex colour like #2952cc.";
  if (Math.max(contrast(value, "#ffffff"), contrast(value, "#111827")) < 4.5)
    return "Too little contrast for readable button text.";
  return undefined;
}

function ColorField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  const error = colorError(value);
  return (
    <Field label={label} error={error}>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value.trim().toLowerCase())}
        disabled={disabled}
        className="font-mono uppercase"
        maxLength={7}
        leading={
          <span
            className="pointer-events-auto relative size-5 overflow-hidden rounded border border-border-strong"
            style={{ background: HEX.test(value) ? value : "transparent" }}
          >
            <input
              type="color"
              value={HEX.test(value) ? value : "#000000"}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              className="absolute inset-0 cursor-pointer opacity-0"
              aria-label={`${label} picker`}
            />
          </span>
        }
      />
    </Field>
  );
}

type Draft = Omit<
  BrandingOut,
  "has_logo" | "version" | "custom_branding_available" | "remove_powered_by_available"
>;

function draftFrom(b: BrandingOut): Draft {
  return {
    display_name: b.display_name,
    short_name: b.short_name ?? "",
    primary_color: b.primary_color,
    accent_color: b.accent_color,
    font_family: b.font_family,
    login_heading: b.login_heading ?? "",
    login_message: b.login_message ?? "",
    footer_text: b.footer_text ?? "",
    support_email: b.support_email ?? "",
    show_powered_by: b.show_powered_by,
  };
}

function Preview({ draft, logoUrl }: { draft: Draft; logoUrl: string | null }) {
  const valid = HEX.test(draft.primary_color);
  const primary = valid ? draft.primary_color : "#2952cc";
  return (
    <div
      className="overflow-hidden rounded-xl border border-border bg-bg shadow-sm"
      aria-label="Login page preview"
    >
      <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-2">
        <span className="size-2 rounded-full bg-border-strong" />
        <span className="size-2 rounded-full bg-border-strong" />
        <span className="size-2 rounded-full bg-border-strong" />
        <span className="ml-2 truncate font-mono text-[11px] text-fg-subtle">{window.location.hostname}</span>
      </div>
      <div
        className="grid grid-cols-[1fr_0.9fr]"
        style={{ fontFamily: draft.font_family === "Inter" ? undefined : draft.font_family }}
      >
        <div className="bg-surface p-5">
          <div className="flex items-center gap-2">
            <TenantMark
              name={draft.display_name || "Institution"}
              logoUrl={logoUrl}
              size={22}
              className="[&]:rounded"
            />
            <span className="truncate text-[11px] font-semibold">
              {draft.short_name || draft.display_name}
            </span>
          </div>
          <p className="mt-6 text-sm font-semibold">Sign in</p>
          <div className="mt-3 h-6 rounded border border-border-strong" />
          <div className="mt-2 h-6 rounded border border-border-strong" />
          <div
            className="mt-3 flex h-6 items-center justify-center rounded text-[10px] font-semibold"
            style={{ background: primary, color: readableOn(primary) }}
          >
            Sign in
          </div>
        </div>
        <div className="p-5" style={{ background: `color-mix(in oklab, ${primary} 9%, white)` }}>
          <p className="text-[9px] font-semibold uppercase tracking-wider" style={{ color: primary }}>
            Results portal
          </p>
          <p className="mt-2 text-[13px] font-semibold leading-tight text-[#101828]">
            {draft.login_heading || `Welcome to ${draft.display_name}`}
          </p>
          <p className="mt-2 line-clamp-4 text-[10px] leading-snug text-[#475467]">
            {draft.login_message || "Sign in to see your published results and download marksheets."}
          </p>
        </div>
      </div>
    </div>
  );
}

const brandingQuery = {
  queryKey: ["branding"],
  queryFn: () => api.get<BrandingOut>("/api/v1/admin/branding"),
};

export function BrandingSettingsPage() {
  const branding = useQuery(brandingQuery);
  if (branding.isPending || !branding.data) return <Skeleton className="h-[520px] rounded-xl" />;
  return <BrandingEditor initial={branding.data} />;
}

function BrandingEditor({ initial }: { initial: BrandingOut }) {
  const qc = useQueryClient();
  const tenant = useTenant();
  const branding = useQuery(brandingQuery);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(initial));
  const [error, setError] = useState<unknown>(null);
  const [removeLogo, setRemoveLogo] = useState(false);

  const afterChange = (data: BrandingOut) => {
    qc.setQueryData(["branding"], data);
    void qc.invalidateQueries({ queryKey: tenantConfigKey });
    void qc.invalidateQueries({ queryKey: ["onboarding"] });
  };

  const save = useMutation({
    mutationFn: (d: Draft) => {
      const custom = saved.custom_branding_available;
      return api.put<BrandingOut>("/api/v1/admin/branding", {
        version: saved.version,
        display_name: d.display_name,
        short_name: d.short_name || null,
        footer_text: d.footer_text || null,
        support_email: d.support_email || null,
        show_powered_by: saved.remove_powered_by_available ? d.show_powered_by : undefined,
        ...(custom
          ? {
              primary_color: d.primary_color,
              accent_color: d.accent_color,
              font_family: d.font_family,
              login_heading: d.login_heading || null,
              login_message: d.login_message || null,
            }
          : {}),
      });
    },
    onSuccess: (data) => {
      afterChange(data);
      setDraft(draftFrom(data));
      toast.success("Branding saved", { description: "Students will see the new look on their next visit." });
    },
    onError: async (e) => {
      setError(e);
      if (e instanceof ApiError && e.status === 409) {
        const fresh = await branding.refetch();
        if (fresh.data) setDraft(draftFrom(fresh.data));
      }
    },
  });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<BrandingOut>("/api/v1/admin/branding/logo", form);
    },
    onSuccess: (data) => {
      afterChange(data);
      toast.success("Logo updated");
    },
    onError: (e) => toastError(e, "Logo upload failed"),
  });
  const remove = useMutation({
    mutationFn: () => api.delete<BrandingOut>("/api/v1/admin/branding/logo"),
    onSuccess: (data) => {
      afterChange(data);
      setRemoveLogo(false);
      toast.success("Logo removed");
    },
    onError: (e) => toastError(e),
  });

  const saved = branding.data ?? initial;
  const dirty = useMemo(() => JSON.stringify(draftFrom(saved)) !== JSON.stringify(draft), [saved, draft]);

  // Live-apply colours while editing, restore the saved theme on leave.
  useEffect(() => {
    if (!saved.custom_branding_available || !HEX.test(draft.primary_color)) return;
    applyBrandTokens({
      ...tenant.branding.tokens,
      primary: draft.primary_color,
      primary_contrast: readableOn(draft.primary_color),
      primary_ink: draft.primary_color,
      accent: draft.accent_color,
      font_family: draft.font_family,
    });
  }, [draft, saved.custom_branding_available, tenant.branding.tokens]);
  useEffect(() => () => applyBrandTokens(tenant.branding.tokens), [tenant.branding.tokens]);

  const b = saved;
  const custom = b.custom_branding_available;
  const set = <K extends keyof Draft>(k: K, value: Draft[K]) => setDraft((d) => ({ ...d, [k]: value }));
  const logoUrl = b.has_logo ? `/api/v1/tenant/logo?v=${b.version}` : null;
  const invalid =
    Boolean(custom && (colorError(draft.primary_color) || colorError(draft.accent_color))) ||
    draft.display_name.trim().length < 2;

  return (
    <div className="grid gap-6 pb-24 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="flex min-w-0 flex-col gap-6">
        {error instanceof ApiError && error.status === 402 && <PlanLimitCallout error={error} />}
        {error instanceof ApiError && error.status === 409 && (
          <Callout tone="warning">Someone else changed the branding. We've loaded their version.</Callout>
        )}
        <Section
          title="Logo"
          description="PNG, JPG or WebP up to 1 MB. A square image at least 256 px wide looks best."
        >
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
            <div className="flex size-24 shrink-0 items-center justify-center rounded-xl border border-border bg-surface-2">
              <TenantMark name={draft.display_name} logoUrl={logoUrl} size={64} />
            </div>
            <div className="min-w-0 flex-1">
              <FileDropzone
                accept="image/png,image/jpeg,image/webp"
                maxBytes={1024 * 1024}
                onFile={(f) => upload.mutate(f)}
                disabled={upload.isPending}
                hint={upload.isPending ? "Uploading…" : "PNG, JPG or WebP · max 1 MB"}
              />
            </div>
          </div>
          {b.has_logo && (
            <div className="mt-4 flex justify-end">
              <Button variant="ghost" size="sm" leadingIcon={<Trash2 />} onClick={() => setRemoveLogo(true)}>
                Remove logo
              </Button>
            </div>
          )}
        </Section>

        <Section title="Name & contact">
          <div className="divide-y divide-border">
            <SettingRow label="Display name" description="Shown in the portal header and emails.">
              <Input
                value={draft.display_name}
                onChange={(e) => set("display_name", e.target.value)}
                maxLength={120}
                aria-label="Display name"
              />
            </SettingRow>
            <SettingRow
              label="Short name"
              description="Used where space is tight, like on phones (optional)."
            >
              <Input
                value={draft.short_name ?? ""}
                onChange={(e) => set("short_name", e.target.value)}
                maxLength={24}
                placeholder="e.g. TIET"
                aria-label="Short name"
              />
            </SettingRow>
            <SettingRow label="Support email" description="Where students should write for help.">
              <Input
                type="email"
                value={draft.support_email ?? ""}
                onChange={(e) => set("support_email", e.target.value)}
                aria-label="Support email"
              />
            </SettingRow>
            <SettingRow label="Footer text">
              <Input
                value={draft.footer_text ?? ""}
                onChange={(e) => set("footer_text", e.target.value)}
                maxLength={300}
                placeholder={`© ${new Date().getFullYear()} ${draft.display_name}`}
                aria-label="Footer text"
              />
            </SettingRow>
          </div>
        </Section>

        <Section
          title="Theme & login page"
          description="Colours, typeface and the welcome text on your sign-in page."
          actions={
            !custom && (
              <Link
                to="/admin/plan"
                className="inline-flex items-center gap-1.5 text-[13px] font-medium text-brand-ink hover:underline"
              >
                <Lock className="size-3.5" aria-hidden /> Available on Starter and above
              </Link>
            )
          }
        >
          <fieldset disabled={!custom} className="divide-y divide-border disabled:opacity-60">
            <SettingRow
              label="Colours"
              description="Buttons use the primary colour; we check it stays readable."
            >
              <div className="grid gap-4 xl:grid-cols-2">
                <ColorField
                  label="Primary"
                  value={draft.primary_color}
                  onChange={(v) => set("primary_color", v)}
                  disabled={!custom}
                />
                <ColorField
                  label="Accent"
                  value={draft.accent_color}
                  onChange={(v) => set("accent_color", v)}
                  disabled={!custom}
                />
              </div>
            </SettingRow>
            <SettingRow label="Typeface">
              <Select
                value={draft.font_family}
                onChange={(e) => set("font_family", e.target.value)}
                className="max-w-xs"
                aria-label="Typeface"
              >
                {FONTS.map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </Select>
            </SettingRow>
            <SettingRow label="Login heading">
              <Input
                value={draft.login_heading ?? ""}
                onChange={(e) => set("login_heading", e.target.value)}
                maxLength={120}
                placeholder={`Welcome to ${draft.display_name}`}
                aria-label="Login heading"
              />
            </SettingRow>
            <SettingRow label="Login message" description="Plain text, up to 600 characters.">
              <Textarea
                value={draft.login_message ?? ""}
                onChange={(e) => set("login_message", e.target.value)}
                maxLength={600}
                rows={3}
                aria-label="Login message"
              />
            </SettingRow>
          </fieldset>
          <div className="mt-5 border-t border-border pt-5">
            <Switch
              label="Show “Powered by ScoreCode”"
              description={
                b.remove_powered_by_available
                  ? "Shown in the footer of your portal."
                  : "Can be hidden on the Pro plan."
              }
              checked={draft.show_powered_by}
              onCheckedChange={(c) => set("show_powered_by", c)}
              disabled={!b.remove_powered_by_available}
            />
          </div>
        </Section>
      </div>

      <aside className="xl:sticky xl:top-8 xl:self-start">
        <p className="mb-2 text-[13px] font-medium text-fg-subtle">Preview</p>
        <Preview draft={draft} logoUrl={logoUrl} />
      </aside>

      <div
        className={
          "fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 backdrop-blur transition-transform duration-200 lg:left-[248px] " +
          (dirty ? "translate-y-0" : "translate-y-full")
        }
        aria-hidden={!dirty}
      >
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-10">
          <p className="text-sm text-fg-muted">Previewing unsaved changes.</p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setDraft(draftFrom(b))} disabled={save.isPending}>
              Discard
            </Button>
            <Button
              onClick={() => {
                setError(null);
                save.mutate(draft);
              }}
              loading={save.isPending}
              disabled={invalid}
            >
              Save branding
            </Button>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={removeLogo}
        onOpenChange={setRemoveLogo}
        title="Remove your logo?"
        description="Your portal and new marksheets will show your initials instead."
        confirmLabel="Remove logo"
        variant="danger"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}
