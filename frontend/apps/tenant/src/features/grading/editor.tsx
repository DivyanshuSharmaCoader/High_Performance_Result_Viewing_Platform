import { api, ApiError, type GradePreview, type GradingSchemeDetail } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  Field,
  Input,
  PageHeader,
  Section,
  Select,
  Skeleton,
  Switch,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Textarea,
  Th,
  formatDateTime,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Save, Trash2, Undo2 } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Link, useParams } from "react-router";

import { toastError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import {
  G,
  STRATEGY_HELP,
  sameConfig,
  toConfig,
  toDraft,
  useInvalidateGrading,
  useScheme,
  type BandDraft,
  type Draft,
} from "./api";

// ---- preview calculator -------------------------------------------------------------------------

interface SamplePaper {
  id: string;
  max: string;
  credits: string;
  mark: string; // a number, or AB (absent) / EX (exempt) as on a mark sheet
}

const DEFAULT_SAMPLES: SamplePaper[] = [
  { id: "Paper 1", max: "100", credits: "4", mark: "86" },
  { id: "Paper 2", max: "100", credits: "4", mark: "64" },
  { id: "Paper 3", max: "100", credits: "3", mark: "38" },
];

function attendanceOf(mark: string): "present" | "absent" | "exempt" {
  const code = mark.trim().toUpperCase();
  return code === "AB" ? "absent" : code === "EX" ? "exempt" : "present";
}

const OUTCOME: Record<string, { label: string; tone: "success" | "danger" | "warning" | "neutral" }> = {
  pass: { label: "Pass", tone: "success" },
  fail: { label: "Fail", tone: "danger" },
  absent: { label: "Absent", tone: "warning" },
  exempt: { label: "Exempt", tone: "neutral" },
  withheld: { label: "Withheld", tone: "warning" },
  incomplete: { label: "Marks missing", tone: "neutral" },
};

function Preview({ draft }: { draft: Draft }) {
  const [samples, setSamples] = useState<SamplePaper[]>(DEFAULT_SAMPLES);
  const credit = draft.strategy === "credit_gpa";
  const request = useDeferredValue(
    JSON.stringify({
      config: toConfig(draft),
      papers: samples.map((s) => ({
        id: s.id,
        credits: credit && s.credits ? s.credits : null,
        components: [{ code: "T", max: s.max || "100" }],
      })),
      marks: Object.fromEntries(
        samples.map((s) => {
          const attendance = attendanceOf(s.mark);
          const mark = s.mark.trim();
          const value = /^\d+(\.\d+)?$/.test(mark) ? mark : null; // anything else: marks missing
          return [s.id, { attendance, components: attendance === "present" ? { T: value } : {} }];
        }),
      ),
    }),
  );
  const result = useQuery({
    queryKey: ["grading", "preview", request],
    queryFn: () => api.post<GradePreview>(`${G}/preview`, JSON.parse(request)),
    placeholderData: (prev) => prev,
    retry: false,
  });
  const set = (i: number, patch: Partial<SamplePaper>) =>
    setSamples((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const r = result.data;
  const invalid = result.error instanceof ApiError ? result.error : null;
  return (
    <Section title="Try it" description="Sample marks graded with the rules on the left, as you edit them.">
      <div className="flex flex-col gap-4">
        <TableContainer>
          <Table>
            <THead>
              <tr>
                <Th>Paper</Th>
                <Th className="w-24">Out of</Th>
                {credit && <Th className="w-20">Credits</Th>}
                <Th className="w-24">Marks</Th>
                <Th className="w-20">Grade</Th>
              </tr>
            </THead>
            <TBody>
              {samples.map((s, i) => {
                const p = r?.papers.find((x) => x.paper_id === s.id);
                return (
                  <tr key={s.id}>
                    <Td className="whitespace-nowrap text-[13px]">{s.id}</Td>
                    <Td>
                      <Input
                        aria-label={`${s.id} maximum marks`}
                        inputMode="decimal"
                        value={s.max}
                        onChange={(e) => set(i, { max: e.target.value })}
                        className="h-8"
                      />
                    </Td>
                    {credit && (
                      <Td>
                        <Input
                          aria-label={`${s.id} credits`}
                          inputMode="decimal"
                          value={s.credits}
                          onChange={(e) => set(i, { credits: e.target.value })}
                          className="h-8"
                        />
                      </Td>
                    )}
                    <Td>
                      <Input
                        aria-label={`${s.id} marks`}
                        value={s.mark}
                        onChange={(e) => set(i, { mark: e.target.value })}
                        className="h-8"
                      />
                    </Td>
                    <Td className="whitespace-nowrap text-[13px]">
                      {p ? (
                        <span
                          className={p.outcome === "fail" ? "font-semibold text-danger" : "font-semibold"}
                        >
                          {p.grade ?? p.percentage ?? "—"}
                          {p.grade_point !== null && (
                            <span className="ml-1 font-normal text-fg-subtle">{p.grade_point}</span>
                          )}
                        </span>
                      ) : (
                        "—"
                      )}
                    </Td>
                  </tr>
                );
              })}
            </TBody>
          </Table>
        </TableContainer>
        <p className="-mt-2 text-xs text-fg-subtle">Type AB for absent or EX for exempt.</p>
        {invalid ? (
          <Callout tone="warning" title="Fix the scheme to see a preview">
            {invalid.detail}
          </Callout>
        ) : r ? (
          <dl
            className="grid grid-cols-2 gap-3 rounded-lg bg-surface-2/60 p-4 text-sm sm:grid-cols-4"
            aria-live="polite"
          >
            <div>
              <dt className="text-xs text-fg-subtle">Result</dt>
              <dd className="mt-1">
                <Badge tone={OUTCOME[r.outcome]?.tone ?? "neutral"}>
                  {OUTCOME[r.outcome]?.label ?? r.outcome}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-fg-subtle">Percentage</dt>
              <dd className="mt-1 font-semibold tabular">
                {r.percentage !== null ? `${r.percentage}%` : "—"}
              </dd>
            </div>
            {draft.strategy === "credit_gpa" ? (
              <div>
                <dt className="text-xs text-fg-subtle">SGPA</dt>
                <dd className="mt-1 font-semibold tabular">{r.sgpa ?? "—"}</dd>
              </div>
            ) : (
              <div>
                <dt className="text-xs text-fg-subtle">Grade</dt>
                <dd className="mt-1 font-semibold">{r.grade ?? "—"}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-fg-subtle">
                {draft.strategy === "credit_gpa" ? "Credits earned" : "Total"}
              </dt>
              <dd className="mt-1 font-semibold tabular">
                {draft.strategy === "credit_gpa"
                  ? `${r.credits_earned ?? "—"} / ${r.credits_attempted ?? "—"}`
                  : r.total !== null
                    ? `${r.total} / ${r.max_total}`
                    : "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <Skeleton className="h-16" />
        )}
      </div>
    </Section>
  );
}

// ---- editor -------------------------------------------------------------------------------------

function BandsEditor({
  draft,
  onChange,
  disabled,
}: {
  draft: Draft;
  onChange: (bands: BandDraft[]) => void;
  disabled: boolean;
}) {
  const credit = draft.strategy === "credit_gpa";
  const update = (i: number, patch: Partial<BandDraft>) =>
    onChange(draft.bands.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  return (
    <div className="flex flex-col gap-3">
      <TableContainer>
        <Table>
          <THead>
            <tr>
              <Th>Grade</Th>
              <Th>From %</Th>
              <Th>{credit ? "Grade points" : "Grade points (optional)"}</Th>
              <Th className="hidden sm:table-cell">Label (optional)</Th>
              <Th className="w-10">
                <span className="sr-only">Remove</span>
              </Th>
            </tr>
          </THead>
          <TBody>
            {draft.bands.map((b, i) => (
              <tr key={i}>
                <Td>
                  <Input
                    aria-label={`Band ${i + 1} grade`}
                    value={b.grade}
                    disabled={disabled}
                    onChange={(e) => update(i, { grade: e.target.value })}
                    className="h-8 w-20 font-semibold"
                  />
                </Td>
                <Td>
                  <Input
                    aria-label={`Band ${i + 1} lowest percentage`}
                    inputMode="decimal"
                    value={b.min_percentage}
                    disabled={disabled || i === draft.bands.length - 1}
                    onChange={(e) => update(i, { min_percentage: e.target.value })}
                    className="h-8 w-20"
                  />
                </Td>
                <Td>
                  <Input
                    aria-label={`Band ${i + 1} grade points`}
                    inputMode="decimal"
                    value={b.grade_point}
                    disabled={disabled}
                    onChange={(e) => update(i, { grade_point: e.target.value })}
                    className="h-8 w-20"
                  />
                </Td>
                <Td className="hidden sm:table-cell">
                  <Input
                    aria-label={`Band ${i + 1} label`}
                    value={b.label}
                    disabled={disabled}
                    onChange={(e) => update(i, { label: e.target.value })}
                    className="h-8"
                  />
                </Td>
                <Td>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove band ${b.grade || i + 1}`}
                    disabled={disabled || draft.bands.length <= 1 || i === draft.bands.length - 1}
                    onClick={() => onChange(draft.bands.filter((_, j) => j !== i))}
                  >
                    <Trash2 />
                  </Button>
                </Td>
              </tr>
            ))}
          </TBody>
        </Table>
      </TableContainer>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-fg-subtle">
          Highest band first. A percentage gets the first band it reaches; the last band always starts at 0%.
        </p>
        {!disabled && (
          <Button
            variant="secondary"
            size="sm"
            leadingIcon={<Plus />}
            onClick={() => {
              const bands = [...draft.bands];
              bands.splice(Math.max(0, bands.length - 1), 0, {
                grade: "",
                min_percentage: "",
                grade_point: "",
                label: "",
              });
              onChange(bands);
            }}
          >
            Add band
          </Button>
        )}
      </div>
    </div>
  );
}

function Editor({ scheme, canManage }: { scheme: GradingSchemeDetail; canManage: boolean }) {
  const invalidate = useInvalidateGrading();
  const saved = toDraft(scheme.config);
  const [draft, setDraft] = useState<Draft>(saved);
  const [name, setName] = useState(scheme.name);
  const [description, setDescription] = useState(scheme.description ?? "");
  const [note, setNote] = useState("");
  const [baseVersion, setBaseVersion] = useState(scheme.version);
  const archived = scheme.archived_at !== null;
  const readOnly = !canManage || archived;
  const configChanged = !sameConfig(draft, saved);
  const detailsChanged = name.trim() !== scheme.name || (description.trim() || null) !== scheme.description;
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  const save = useMutation({
    mutationFn: async () => {
      let latest = scheme;
      if (detailsChanged)
        latest = await api.put<GradingSchemeDetail>(`${G}/${scheme.id}`, {
          name: name.trim(),
          description: description.trim() || null,
        });
      if (configChanged)
        latest = await api.post<GradingSchemeDetail>(`${G}/${scheme.id}/versions`, {
          config: toConfig(draft),
          note: note.trim() || null,
          based_on: baseVersion,
        });
      return latest;
    },
    onSuccess: (s) => {
      invalidate(s);
      setBaseVersion(s.version);
      setDraft(toDraft(s.config));
      setNote("");
      toast.success(configChanged ? `Saved as version ${s.version}` : "Saved");
    },
    onError: (e) => toastError(e),
  });

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(360px,440px)]">
      <div className="flex flex-col gap-5">
        <Section title="Details">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Name">
              <Input value={name} disabled={readOnly} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Kind" description={STRATEGY_HELP[scheme.strategy]}>
              <Input value={scheme.strategy_label} readOnly disabled />
            </Field>
          </div>
          <Field label="Description" optional className="mt-5">
            <Textarea
              rows={2}
              value={description}
              disabled={readOnly}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
        </Section>

        {draft.strategy !== "marks_only" && (
          <Section title="Grade bands">
            <BandsEditor draft={draft} disabled={readOnly} onChange={(bands) => set({ bands })} />
          </Section>
        )}

        <Section title="Pass rules">
          <div className="flex flex-col gap-5">
            <div className="grid gap-5 sm:grid-cols-2">
              <Field
                label="Pass mark per paper (%)"
                optional
                description="Used when a paper has no pass mark of its own."
              >
                <Input
                  inputMode="decimal"
                  value={draft.paper_pass_percentage}
                  disabled={readOnly}
                  onChange={(e) => set({ paper_pass_percentage: e.target.value })}
                />
              </Field>
              <Field label="Overall pass mark (%)" optional>
                <Input
                  inputMode="decimal"
                  value={draft.overall_pass_percentage}
                  disabled={readOnly}
                  onChange={(e) => set({ overall_pass_percentage: e.target.value })}
                />
              </Field>
            </div>
            <Switch
              checked={draft.require_all_papers}
              disabled={readOnly}
              onCheckedChange={(v) => set({ require_all_papers: v })}
              label="Every paper must be passed"
              description="A failed or absent paper fails the whole exam."
            />
            {draft.strategy !== "marks_only" && (
              <div className="grid gap-5 sm:grid-cols-2">
                <Field
                  label="Grade for a failed paper"
                  optional={draft.strategy === "percentage_bands"}
                  description={
                    draft.strategy === "percentage_bands"
                      ? "Leave empty to show the band grade."
                      : "Earns 0 grade points."
                  }
                >
                  <Input
                    value={draft.fail_grade}
                    disabled={readOnly}
                    onChange={(e) => set({ fail_grade: e.target.value })}
                    className="w-28"
                  />
                </Field>
                <Field label="Grade for an absent paper" optional>
                  <Input
                    value={draft.absent_grade}
                    disabled={readOnly}
                    onChange={(e) => set({ absent_grade: e.target.value })}
                    className="w-28"
                  />
                </Field>
              </div>
            )}
            {draft.strategy === "credit_gpa" && (
              <Switch
                checked={draft.count_absent_as_attempted}
                disabled={readOnly}
                onCheckedChange={(v) => set({ count_absent_as_attempted: v })}
                label="Absent papers count towards SGPA"
                description="Their credits are attempted with 0 grade points."
              />
            )}
            {draft.strategy === "marks_only" && (
              <Field label="Ranks">
                <Select
                  value={draft.ranking}
                  disabled={readOnly}
                  onChange={(e) => set({ ranking: e.target.value as Draft["ranking"] })}
                  className="sm:w-80"
                >
                  <option value="competition">Equal scores share a rank, next rank skips (1, 2, 2, 4)</option>
                  <option value="dense">Equal scores share a rank, no gaps (1, 2, 2, 3)</option>
                  <option value="none">No ranks</option>
                </Select>
              </Field>
            )}
          </div>
        </Section>

        <Section title="Rounding">
          <div className="grid gap-5 sm:grid-cols-3">
            <Field label="Rounding">
              <Select
                value={draft.rounding_mode}
                disabled={readOnly}
                onChange={(e) => set({ rounding_mode: e.target.value as Draft["rounding_mode"] })}
              >
                <option value="half_up">Half up</option>
                <option value="half_even">Half to even</option>
                <option value="down">Always down</option>
                <option value="up">Always up</option>
              </Select>
            </Field>
            <Field label="Percentage decimals">
              <Select
                value={String(draft.percentage_places)}
                disabled={readOnly}
                onChange={(e) => set({ percentage_places: Number(e.target.value) })}
              >
                {[0, 1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </Field>
            {draft.strategy !== "marks_only" && (
              <Field label="Grade point decimals">
                <Select
                  value={String(draft.gpa_places)}
                  disabled={readOnly}
                  onChange={(e) => set({ gpa_places: Number(e.target.value) })}
                >
                  {[0, 1, 2, 3].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
          </div>
          <p className="mt-3 text-[13px] text-fg-subtle">
            Grades use the rounded percentage — the figure students see.
          </p>
        </Section>

        {!readOnly && (configChanged || detailsChanged || save.isPending) && (
          <div className="sticky bottom-0 z-10 flex flex-col gap-3 rounded-xl border border-border bg-surface/95 p-4 shadow-md backdrop-blur sm:flex-row sm:items-end">
            {configChanged && (
              <Field label="What changed?" optional className="flex-1">
                <Input
                  value={note}
                  maxLength={200}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Pass mark raised to 35%"
                />
              </Field>
            )}
            <div className="flex gap-2 sm:ml-auto">
              <Button
                variant="ghost"
                leadingIcon={<Undo2 />}
                disabled={!configChanged && !detailsChanged}
                onClick={() => {
                  setDraft(saved);
                  setName(scheme.name);
                  setDescription(scheme.description ?? "");
                }}
              >
                Discard
              </Button>
              <Button
                leadingIcon={<Save />}
                disabled={!configChanged && !detailsChanged}
                loading={save.isPending}
                onClick={() => save.mutate()}
              >
                {configChanged ? `Save as version ${scheme.version + 1}` : "Save"}
              </Button>
            </div>
          </div>
        )}

        <Section title="Version history" description="Exams keep the version they were processed with.">
          <ol className="flex flex-col gap-2">
            {scheme.versions.map((v) => (
              <li key={v.id} className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                <span className="font-semibold text-fg">Version {v.version}</span>
                <span className="text-fg-subtle">
                  {formatDateTime(v.created_at)}
                  {v.created_by_name && ` · ${v.created_by_name}`}
                </span>
                {v.note && <span className="w-full text-fg-muted">{v.note}</span>}
              </li>
            ))}
          </ol>
        </Section>
      </div>
      <div className="xl:sticky xl:top-6 xl:self-start">
        <Preview draft={draft} />
      </div>
    </div>
  );
}

export default function GradingEditorPage() {
  const { schemeId = "" } = useParams();
  const canManage = useCan("grading.manage");
  const q = useScheme(schemeId);
  if (q.isPending) return <Skeleton className="h-96 w-full" />;
  if (q.error) return <Callout tone="danger">This grading scheme couldn't be loaded.</Callout>;
  const s = q.data;
  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/admin/grading">Grading</Link>}
        title={s.name}
        meta={
          <>
            <Badge tone="info">{s.strategy_label}</Badge>
            {s.is_default && <Badge tone="brand">Default</Badge>}
            {s.archived_at && <Badge>Archived — restore it to make changes</Badge>}
            <span className="text-[13px] text-fg-subtle">Version {s.version}</span>
          </>
        }
      />
      <Editor key={`${s.id}:${s.version}`} scheme={s} canManage={canManage} />
    </>
  );
}
