import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError, type SettingsOut } from "@scorecode/api-client";
import {
  Button,
  Callout,
  Field,
  Input,
  PageHeader,
  RadioCards,
  Section,
  Select,
  SettingRow,
  Skeleton,
  Switch,
  Textarea,
  cn,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { NavLink, Outlet } from "react-router";
import { z } from "zod";

import { PlanLimitCallout } from "../../components/limit-callout";
import { applyServerError } from "../../lib/forms";
import { useFeature } from "../../lib/tenant";

export function SettingsLayout() {
  const tabs = [
    { to: "/admin/settings", label: "Institution", end: true },
    { to: "/admin/settings/branding", label: "Branding", end: false },
  ];
  return (
    <>
      <PageHeader title="Settings" description="How your institution appears and how results are handled." />
      <nav aria-label="Settings sections" className="mb-6 flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              cn(
                "-mb-px inline-flex h-10 items-center border-b-2 px-3 text-sm font-medium transition-colors",
                isActive ? "border-brand text-fg" : "border-transparent text-fg-subtle hover:text-fg",
              )
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}

const schema = z.object({
  official_name: z.string().trim().min(2, "Enter your institution's official name").max(200),
  address: z.string().trim().max(500),
  affiliation: z.string().trim().max(200),
  contact_email: z.union([z.literal(""), z.email("Enter a valid email address")]),
  contact_phone: z.union([
    z.literal(""),
    z
      .string()
      .trim()
      .regex(/^[0-9+()\-\s]{6,32}$/, "Enter a valid phone number"),
  ]),
  approval_mode: z.enum(["single", "maker_checker"]),
  student_activation_mode: z.enum(["code", "email"]),
  verification_disclosure: z.enum(["masked", "masked_plus_challenge"]),
  student_stats: z.enum(["none", "class_average", "full"]),
  publish_notify_email: z.boolean(),
  locale: z.enum(["en-IN", "hi-IN", "pa-IN"]),
});
type Values = z.infer<typeof schema>;

function toValues(s: SettingsOut): Values {
  return {
    official_name: s.official_name,
    address: s.address ?? "",
    affiliation: s.affiliation ?? "",
    contact_email: s.contact_email ?? "",
    contact_phone: s.contact_phone ?? "",
    approval_mode: s.approval_mode as Values["approval_mode"],
    student_activation_mode: s.student_activation_mode as Values["student_activation_mode"],
    verification_disclosure: s.verification_disclosure as Values["verification_disclosure"],
    student_stats: s.student_stats as Values["student_stats"],
    publish_notify_email: s.publish_notify_email,
    locale: (["en-IN", "hi-IN", "pa-IN"].includes(s.locale) ? s.locale : "en-IN") as Values["locale"],
  };
}

export function InstitutionSettingsPage() {
  const qc = useQueryClient();
  const makerChecker = useFeature("maker_checker_approval");
  const challenge = useFeature("verification_challenge");
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsOut>("/api/v1/admin/settings"),
  });
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const v = useWatch({ control: form.control }) as Values;
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (settings.data) form.reset(toValues(settings.data));
  }, [settings.data, form]);

  const save = useMutation({
    mutationFn: (v: Values) =>
      api.put<SettingsOut>("/api/v1/admin/settings", {
        ...v,
        version: settings.data?.version,
        address: v.address || null,
        affiliation: v.affiliation || null,
        contact_email: v.contact_email || null,
        contact_phone: v.contact_phone || null,
      }),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      void qc.invalidateQueries({ queryKey: ["onboarding"] });
      form.reset(toValues(data));
      toast.success("Settings saved");
    },
    onError: (e) => {
      const msg = applyServerError(e, form.setError, Object.keys(schema.shape));
      setError(msg ? e : null);
      if (e instanceof ApiError && e.status === 409) void settings.refetch();
    },
  });

  if (settings.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );
  }
  const dirty = form.formState.isDirty;
  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((values) => {
        setError(null);
        save.mutate(values);
      })}
      className="flex flex-col gap-6 pb-24"
    >
      {error instanceof ApiError && error.status === 402 && <PlanLimitCallout error={error} />}
      {error instanceof ApiError && error.status === 409 && (
        <Callout tone="warning" title="Someone else saved changes">
          We've loaded the latest settings. Review them and save again.
        </Callout>
      )}
      <Section
        title="Institution profile"
        description="Printed on marksheets and shown on the verification page."
      >
        <div className="divide-y divide-border">
          <SettingRow label="Official name" description="Exactly as it should appear on marksheets.">
            <Field
              label="Official name"
              error={form.formState.errors.official_name?.message}
              className="[&_label]:sr-only"
            >
              <Input {...form.register("official_name")} />
            </Field>
          </SettingRow>
          <SettingRow label="Address">
            <Field
              label="Address"
              error={form.formState.errors.address?.message}
              className="[&_label]:sr-only"
            >
              <Textarea rows={3} {...form.register("address")} />
            </Field>
          </SettingRow>
          <SettingRow label="Affiliation" description="Board, university or accreditation (optional).">
            <Field label="Affiliation" className="[&_label]:sr-only">
              <Input placeholder="e.g. Affiliated to CBSE, New Delhi" {...form.register("affiliation")} />
            </Field>
          </SettingRow>
          <SettingRow label="Contact" description="Shown to students who need help.">
            <div className="grid gap-4 xl:grid-cols-2">
              <Field label="Email" error={form.formState.errors.contact_email?.message}>
                <Input type="email" {...form.register("contact_email")} />
              </Field>
              <Field label="Phone" error={form.formState.errors.contact_phone?.message} optional>
                <Input type="tel" {...form.register("contact_phone")} />
              </Field>
            </div>
          </SettingRow>
        </div>
      </Section>

      <Section title="Results policy" description="How results are approved, shared and verified.">
        <div className="divide-y divide-border">
          <SettingRow
            label="Approval before publishing"
            description="Who must sign off on processed results."
          >
            <RadioCards
              name="approval_mode"
              columns={1}
              value={v.approval_mode}
              onChange={(x) => form.setValue("approval_mode", x, { shouldDirty: true })}
              options={[
                {
                  value: "single",
                  label: "One administrator",
                  description: "Any administrator can approve and publish.",
                },
                {
                  value: "maker_checker",
                  label: "Two-person approval",
                  description: "The person who processed results can't approve them.",
                  disabled: !makerChecker && v.approval_mode !== "maker_checker",
                  badge: !makerChecker ? (
                    <span className="text-xs font-normal text-fg-subtle">Growth plan</span>
                  ) : undefined,
                },
              ]}
            />
          </SettingRow>
          <SettingRow
            label="Student activation"
            description="How students set up their accounts."
            labelFor="setting-student_activation_mode"
          >
            <Select
              id="setting-student_activation_mode"
              {...form.register("student_activation_mode")}
              className="max-w-xs"
            >
              <option value="code">Printed activation codes</option>
              <option value="email">Email invitation</option>
            </Select>
          </SettingRow>
          <SettingRow
            label="Verification page"
            description="What third parties see when they scan a marksheet's QR code."
            labelFor="setting-verification_disclosure"
          >
            <Select
              id="setting-verification_disclosure"
              {...form.register("verification_disclosure")}
              className="max-w-md"
            >
              <option value="masked">Masked name and status only</option>
              <option
                value="masked_plus_challenge"
                disabled={!challenge && v.verification_disclosure !== "masked_plus_challenge"}
              >
                Full result after date-of-birth check{!challenge ? " (Pro plan)" : ""}
              </option>
            </Select>
          </SettingRow>
          <SettingRow
            label="Class statistics for students"
            description="Aggregates students can see next to their result."
            labelFor="setting-student_stats"
          >
            <Select id="setting-student_stats" {...form.register("student_stats")} className="max-w-xs">
              <option value="none">None</option>
              <option value="class_average">Class average only</option>
              <option value="full">Average, highest and distribution</option>
            </Select>
          </SettingRow>
          <SettingRow
            label="Language for students and marksheets"
            description="Students and parents see their results in this language (they can switch on their own phone). In Hindi or Punjabi, marksheets carry English and that language side by side. Staff screens stay in English."
            labelFor="setting-locale"
          >
            <Select id="setting-locale" {...form.register("locale")} className="max-w-xs">
              <option value="en-IN">English</option>
              <option value="hi-IN" lang="hi">
                हिन्दी (Hindi)
              </option>
              <option value="pa-IN" lang="pa">
                ਪੰਜਾਬੀ (Punjabi)
              </option>
            </Select>
          </SettingRow>
          <SettingRow label="Email on publication" description="Emails contain a link only — never marks.">
            <Switch
              label="Email students when results are published"
              checked={v.publish_notify_email}
              onCheckedChange={(c) => form.setValue("publish_notify_email", c, { shouldDirty: true })}
            />
          </SettingRow>
        </div>
      </Section>

      <div
        className={cn(
          "fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 backdrop-blur transition-transform duration-200 lg:left-[248px]",
          dirty ? "translate-y-0" : "translate-y-full",
        )}
        inert={!dirty} // off-screen with nothing to save: out of the tab order and the accessibility tree
      >
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-10">
          <p className="text-sm text-fg-muted">You have unsaved changes.</p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => settings.data && form.reset(toValues(settings.data))}
              disabled={save.isPending}
            >
              Discard
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save changes
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
