import { api, type GradingScheme, type GradingSchemeDetail } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  PageHeader,
  RadioCards,
  Skeleton,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Award, MoreHorizontal, Plus, Star } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { FormDialog } from "../../components/form-dialog";
import { applyServerError, toastError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { G, useInvalidateGrading, useSchemes, useTemplates } from "./api";

function NewSchemeDialog({ onClose }: { onClose: () => void }) {
  const templates = useTemplates();
  const navigate = useNavigate();
  const invalidate = useInvalidateGrading();
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | undefined>();
  const [error, setError] = useState<unknown>(null);
  const chosen = templates.data?.find((t) => t.key === (key || templates.data?.[0]?.key));
  const create = useMutation({
    mutationFn: () =>
      api.post<GradingSchemeDetail>(G, { name: name.trim() || chosen?.name, config: chosen?.config }),
    onSuccess: (s) => {
      invalidate(s);
      toast.success(`“${s.name}” created`, { description: "Adjust the bands and rules, then save." });
      void navigate(`/admin/grading/${s.id}`);
    },
    onError: (e) => {
      const msg = applyServerError(e, (_f, m) => setNameError(m.message), ["name"]);
      setError(msg ? e : null);
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="New grading scheme"
      description="Start from a common scale — every band, pass mark and rounding rule can be changed afterwards."
      submitLabel="Create scheme"
      submitting={create.isPending}
      error={error}
      formId="new-scheme"
      size="lg"
    >
      <form
        id="new-scheme"
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setNameError(undefined);
          create.mutate();
        }}
      >
        {templates.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <Field label="Start from">
            <RadioCards
              name="template"
              value={chosen?.key ?? ""}
              onChange={setKey}
              options={(templates.data ?? []).map((t) => ({
                value: t.key,
                label: t.name,
                description: t.description,
              }))}
            />
          </Field>
        )}
        <Field label="Name" error={nameError} description="As staff will see it when setting up an exam.">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={chosen?.name} />
        </Field>
      </form>
    </FormDialog>
  );
}

function SchemeCard({ scheme, canManage }: { scheme: GradingScheme; canManage: boolean }) {
  const invalidate = useInvalidateGrading();
  const [confirmArchive, setConfirmArchive] = useState(false);
  const archived = scheme.archived_at !== null;
  const makeDefault = useMutation({
    mutationFn: () => api.post<GradingSchemeDetail>(`${G}/${scheme.id}/default`),
    onSuccess: (s) => {
      invalidate(s);
      toast.success(`“${s.name}” is now the default`);
    },
    onError: (e) => toastError(e),
  });
  const archive = useMutation({
    mutationFn: () => api.put<GradingSchemeDetail>(`${G}/${scheme.id}/archived`, { archived: !archived }),
    onSuccess: (s) => {
      invalidate(s);
      setConfirmArchive(false);
      toast.success(archived ? "Scheme restored" : "Scheme archived");
    },
    onError: (e) => {
      setConfirmArchive(false);
      toastError(e);
    },
  });
  return (
    <li className="relative flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-xs hover:border-border-strong">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={`/admin/grading/${scheme.id}`}
            className="text-[15px] font-semibold text-fg after:absolute after:inset-0 hover:underline"
          >
            {scheme.name}
          </Link>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Badge tone="info">{scheme.strategy_label}</Badge>
            {scheme.is_default && (
              <Badge tone="brand" icon={<Star />}>
                Default
              </Badge>
            )}
            {archived && <Badge>Archived</Badge>}
          </div>
        </div>
        {canManage && (
          <Menu>
            <MenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="relative z-10"
                aria-label={`Actions for ${scheme.name}`}
              >
                <MoreHorizontal />
              </Button>
            </MenuTrigger>
            <MenuContent align="end">
              {!scheme.is_default && !archived && (
                <MenuItem icon={<Star />} onSelect={() => makeDefault.mutate()}>
                  Make default
                </MenuItem>
              )}
              {archived ? (
                <MenuItem icon={<ArchiveRestore />} onSelect={() => archive.mutate()}>
                  Restore
                </MenuItem>
              ) : (
                <MenuItem icon={<Archive />} destructive onSelect={() => setConfirmArchive(true)}>
                  Archive
                </MenuItem>
              )}
            </MenuContent>
          </Menu>
        )}
      </div>
      {scheme.description && <p className="text-[13px] leading-5 text-fg-muted">{scheme.description}</p>}
      <p className="mt-auto text-xs text-fg-subtle">
        Version {scheme.version} · updated {formatRelative(scheme.updated_at)}
      </p>
      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={setConfirmArchive}
        title={`Archive “${scheme.name}”?`}
        description="It won't be offered for new exams. Exams that already use it keep their results."
        confirmLabel="Archive"
        variant="danger"
        loading={archive.isPending}
        onConfirm={() => archive.mutate()}
      />
    </li>
  );
}

export default function GradingPage() {
  const canManage = useCan("grading.manage");
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const schemes = useSchemes(archived);
  const rows = schemes.data ?? [];
  return (
    <>
      <PageHeader
        title="Grading"
        description="How marks become results: grade bands, grade points and credits, pass rules and rounding. Each saved change is a new version, so exams already processed keep their rules."
        actions={
          canManage && (
            <Button leadingIcon={<Plus />} onClick={() => setCreating(true)}>
              New scheme
            </Button>
          )
        }
      />
      <div className="mb-4">
        <Checkbox checked={archived} onCheckedChange={setArchived} label="Show archived" />
      </div>
      {schemes.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface">
          <EmptyState
            icon={<Award />}
            title="No grading scheme yet"
            description="Pick a starting point — a board-style band scale, a credit/SGPA scale or marks with ranks — and adjust it to your rules."
            action={
              canManage && (
                <Button leadingIcon={<Plus />} onClick={() => setCreating(true)}>
                  Create a scheme
                </Button>
              )
            }
          />
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Grading schemes">
          {rows.map((s) => (
            <SchemeCard key={s.id} scheme={s} canManage={canManage} />
          ))}
        </ul>
      )}
      {creating && <NewSchemeDialog onClose={() => setCreating(false)} />}
    </>
  );
}
