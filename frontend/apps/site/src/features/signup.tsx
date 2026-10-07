import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError } from "@scorecode/api-client";
import {
  Button,
  Callout,
  Field,
  Input,
  PasswordInput,
  PasswordStrength,
  Select,
  Spinner,
} from "@scorecode/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, MailCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { applyFieldErrors } from "../lib/forms";

const SLUG = /^[a-z0-9](-?[a-z0-9]){2,30}$/;

const schema = z.object({
  institution_name: z.string().trim().min(3, "Enter your institution's name").max(200),
  institution_type: z.enum(["school", "college", "university", "coaching", "other"], {
    message: "Choose a type",
  }),
  slug: z.string().trim().toLowerCase().regex(SLUG, "3–31 lowercase letters, numbers or single hyphens"),
  full_name: z.string().trim().min(2, "Enter your name").max(200),
  email: z.email("Enter a valid email address"),
  phone: z.union([
    z.literal(""),
    z
      .string()
      .trim()
      .regex(/^[0-9+()\-\s]{6,32}$/, "Enter a valid phone number"),
  ]),
  password: z.string().min(12, "Use at least 12 characters"),
  website: z.string().optional(), // the honeypot: people never see it, form-filling bots fill it
});
type Values = z.input<typeof schema>;

function suggestSlug(name: string): string {
  const words = name
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s-]/g, "")
    .split(/\s+/)
    .filter((w) => w && !["of", "the", "and", "for"].includes(w));
  const initials = words.map((w) => w[0]).join("");
  const candidate = words.length > 3 ? initials : words.join("-");
  return candidate.replace(/-+/g, "-").slice(0, 31).replace(/^-|-$/g, "");
}

function useBaseDomain(): string {
  return window.location.hostname.replace(/^www\./, "");
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function SlugStatus({ slug }: { slug: string }) {
  const debounced = useDebounced(slug, 350);
  const valid = SLUG.test(debounced);
  const q = useQuery({
    queryKey: ["slug", debounced],
    queryFn: () =>
      api.get<{ available: boolean; reason: string | null }>("/api/v1/signup/slug-availability", {
        query: { slug: debounced },
      }),
    enabled: valid,
    staleTime: 15_000,
  });
  if (!slug || !SLUG.test(slug)) return null;
  if (debounced !== slug || q.isPending) {
    return (
      <span className="flex items-center gap-1.5 text-[13px] text-fg-subtle" aria-live="polite">
        <Spinner className="size-3.5" /> Checking…
      </span>
    );
  }
  if (q.isError) {
    return (
      <span className="text-[13px] text-fg-subtle" aria-live="polite">
        Couldn't check right now
      </span>
    );
  }
  if (q.data.available) {
    return (
      <span className="flex items-center gap-1.5 text-[13px] text-success" aria-live="polite">
        <CheckCircle2 className="size-3.5" /> Available
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[13px] text-danger" aria-live="polite">
      <XCircle className="size-3.5" /> {q.data.reason ?? "Not available"}
    </span>
  );
}

export default function SignupPage() {
  const base = useBaseDomain();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      institution_name: "",
      institution_type: "school",
      slug: "",
      full_name: "",
      email: "",
      phone: "",
      password: "",
      website: "",
    },
  });
  const slug = useWatch({ control: form.control, name: "slug" });
  const password = useWatch({ control: form.control, name: "password" });
  const signup = useMutation({
    mutationFn: (v: z.output<typeof schema>) =>
      api.post<{ email: string }>("/api/v1/signup", {
        ...v,
        phone: v.phone || null,
        website: v.website || null,
      }),
    onSuccess: (data) => setSentTo(data.email),
    onError: (e) => {
      if (e instanceof ApiError && e.status === 429) {
        setFormError("Too many sign-ups from your network. Please try again in an hour.");
        return;
      }
      setFormError(applyFieldErrors(e, form.setError, Object.keys(schema.shape)));
    },
  });

  if (sentTo) {
    return (
      <div className="mx-auto max-w-md px-5 py-24 text-center animate-slide-up">
        <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-brand-soft text-brand-ink">
          <MailCheck className="size-6" aria-hidden />
        </span>
        <h1 className="mt-6 text-2xl font-semibold tracking-[-0.02em]">Check your email</h1>
        <p className="mt-3 text-[15px] leading-7 text-fg-muted">
          We sent a confirmation link to <span className="font-medium text-fg">{sentTo}</span>. Open it within
          30 minutes to create your portal at{" "}
          <span className="font-medium text-fg">
            {form.getValues("slug")}.{base}
          </span>
          .
        </p>
        <p className="mt-6 text-[13px] text-fg-subtle">
          Didn't get it? Check spam, or{" "}
          <button
            type="button"
            className="font-medium text-brand-ink hover:underline"
            onClick={() => setSentTo(null)}
          >
            go back and try again
          </button>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-12 px-5 py-14 lg:grid-cols-[minmax(0,1fr)_420px] lg:py-20">
      <div className="max-w-md">
        <h1 className="text-3xl font-semibold tracking-[-0.02em]">
          Create your institution's results portal
        </h1>
        <p className="mt-4 text-[15px] leading-7 text-fg-muted">
          You'll be the owner and can invite administrators and faculty next. The free plan covers up to 150
          students — upgrade any time without losing data.
        </p>
        <ul className="mt-8 flex flex-col gap-3 text-sm text-fg-muted">
          {[
            "Your own portal address and branding",
            "Spreadsheet import with error reports",
            "Verifiable marksheets with QR codes",
          ].map((t) => (
            <li key={t} className="flex gap-2.5">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
              {t}
            </li>
          ))}
        </ul>
      </div>
      <form
        noValidate
        onSubmit={form.handleSubmit((v) => {
          setFormError(null);
          signup.mutate(schema.parse(v));
        })}
        className="flex flex-col gap-5 rounded-xl border border-border bg-surface p-6 shadow-sm"
      >
        {formError && <Callout tone="danger">{formError}</Callout>}
        <Field label="Institution name" error={form.formState.errors.institution_name?.message}>
          <Input
            autoComplete="organization"
            {...form.register("institution_name", {
              onChange: (e: { target: { value: string } }) => {
                if (!slugTouched) form.setValue("slug", suggestSlug(e.target.value));
              },
            })}
          />
        </Field>
        <Field label="Type" error={form.formState.errors.institution_type?.message}>
          <Select {...form.register("institution_type")}>
            <option value="school">School</option>
            <option value="college">College</option>
            <option value="university">University</option>
            <option value="coaching">Coaching institute</option>
            <option value="other">Other</option>
          </Select>
        </Field>
        <Field
          label="Portal address"
          error={form.formState.errors.slug?.message}
          aside={<SlugStatus slug={slug} />}
        >
          <Input
            autoCapitalize="none"
            spellCheck={false}
            className="pr-36 font-mono"
            trailing={
              <span className="pointer-events-none pr-1 font-mono text-[13px] text-fg-subtle">.{base}</span>
            }
            {...form.register("slug", { onChange: () => setSlugTouched(true) })}
            value={slug}
          />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Your name" error={form.formState.errors.full_name?.message}>
            <Input autoComplete="name" {...form.register("full_name")} />
          </Field>
          <Field label="Phone" optional error={form.formState.errors.phone?.message}>
            <Input type="tel" autoComplete="tel" {...form.register("phone")} />
          </Field>
        </div>
        <Field label="Work email" error={form.formState.errors.email?.message}>
          <Input type="email" autoComplete="email" {...form.register("email")} />
        </Field>
        <Field label="Password" error={form.formState.errors.password?.message}>
          <PasswordInput autoComplete="new-password" {...form.register("password")} />
        </Field>
        <PasswordStrength value={password} minLength={12} />
        {/* Not for people: off-screen, out of the tab order, hidden from screen readers (docs/10 §7). */}
        <div aria-hidden="true" className="absolute -left-[10000px] top-auto size-px overflow-hidden">
          <label>
            Website
            <input type="text" tabIndex={-1} autoComplete="off" {...form.register("website")} />
          </label>
        </div>
        <Button type="submit" size="lg" loading={signup.isPending}>
          Create portal
        </Button>
        <p className="text-center text-xs leading-5 text-fg-subtle">
          By continuing you agree to process student data only for your institution's academic purposes.{" "}
          <Link to="/" className="hover:underline">
            Back to home
          </Link>
        </p>
      </form>
    </div>
  );
}
