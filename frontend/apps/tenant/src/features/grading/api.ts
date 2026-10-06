import {
  api,
  type GradingScheme,
  type GradingSchemeDetail,
  type GradingStrategy,
  type GradingTemplate,
} from "@scorecode/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";

export const G = "/api/v1/admin/grading-schemes";

export const gradingKeys = {
  all: ["grading"] as const,
  list: (archived: boolean) => ["grading", "list", archived] as const,
  one: (id: string) => ["grading", "one", id] as const,
  templates: ["grading", "templates"] as const,
};

export const useSchemes = (archived = false) =>
  useQuery({
    queryKey: gradingKeys.list(archived),
    queryFn: () => api.get<GradingScheme[]>(G, { query: { include_archived: archived } }),
  });

export const useScheme = (id: string) =>
  useQuery({ queryKey: gradingKeys.one(id), queryFn: () => api.get<GradingSchemeDetail>(`${G}/${id}`) });

export const useTemplates = () =>
  useQuery({
    queryKey: gradingKeys.templates,
    queryFn: () => api.get<GradingTemplate[]>(`${G}/templates`),
    staleTime: Infinity,
  });

export function useInvalidateGrading() {
  const qc = useQueryClient();
  return (scheme?: GradingSchemeDetail) => {
    if (scheme) qc.setQueryData(gradingKeys.one(scheme.id), scheme);
    void qc.invalidateQueries({ queryKey: gradingKeys.all });
    void qc.invalidateQueries({ queryKey: ["onboarding"] });
  };
}

export const STRATEGY_HELP: Record<GradingStrategy, string> = {
  percentage_bands: "Each percentage band gives a grade (and optionally grade points).",
  credit_gpa: "Grade points weighted by course credits give an SGPA.",
  marks_only: "Totals, percentages and ranks — no grades.",
};

// ---- the editable shape of a scheme config ---------------------------------------------------------

export interface BandDraft {
  grade: string;
  min_percentage: string;
  grade_point: string;
  label: string;
}

export interface Draft {
  strategy: GradingStrategy;
  bands: BandDraft[];
  fail_grade: string;
  absent_grade: string;
  paper_pass_percentage: string;
  overall_pass_percentage: string;
  require_all_papers: boolean;
  rounding_mode: "half_up" | "half_even" | "down" | "up";
  percentage_places: number;
  gpa_places: number;
  total_places: number;
  ranking: "competition" | "dense" | "none";
  count_absent_as_attempted: boolean;
}

const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
/** "91.000" → "91", "8.50" → "8.5": what a person would type. */
const num = (v: unknown): string => {
  const s = str(v);
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
};

export function toDraft(config: Record<string, unknown>): Draft {
  const c = config;
  const rules = (c.pass_rules ?? {}) as Record<string, unknown>;
  const rounding = (c.rounding ?? {}) as Record<string, unknown>;
  return {
    strategy: c.strategy as GradingStrategy,
    bands: ((c.bands as Record<string, unknown>[] | undefined) ?? []).map((b) => ({
      grade: str(b.grade),
      min_percentage: num(b.min_percentage),
      grade_point: num(b.grade_point),
      label: str(b.label),
    })),
    fail_grade: str(c.fail_grade),
    absent_grade: c.absent_grade === undefined ? "AB" : str(c.absent_grade),
    paper_pass_percentage: num(rules.paper_pass_percentage),
    overall_pass_percentage: num(rules.overall_pass_percentage),
    require_all_papers: rules.require_all_papers !== false,
    rounding_mode: (rounding.mode as Draft["rounding_mode"]) ?? "half_up",
    percentage_places: Number(rounding.percentage_places ?? 2),
    gpa_places: Number(rounding.gpa_places ?? 2),
    total_places: Number(rounding.total_places ?? 2),
    ranking: (c.ranking as Draft["ranking"]) ?? "competition",
    count_absent_as_attempted: c.count_absent_as_attempted !== false,
  };
}

const orNull = (s: string) => (s.trim() === "" ? null : s.trim());

/** The config the API stores. Only keys that apply to the strategy are sent. */
export function toConfig(d: Draft): Record<string, unknown> {
  const base: Record<string, unknown> = {
    strategy: d.strategy,
    absent_grade: orNull(d.absent_grade),
    pass_rules: {
      paper_pass_percentage: orNull(d.paper_pass_percentage),
      overall_pass_percentage: orNull(d.overall_pass_percentage),
      require_all_papers: d.require_all_papers,
    },
    rounding: {
      mode: d.rounding_mode,
      percentage_places: d.percentage_places,
      gpa_places: d.gpa_places,
      total_places: d.total_places,
    },
  };
  if (d.strategy === "marks_only") return { ...base, ranking: d.ranking };
  const bands = d.bands.map((b) => ({
    grade: b.grade.trim(),
    min_percentage: b.min_percentage.trim(),
    grade_point: orNull(b.grade_point),
    label: orNull(b.label),
  }));
  if (d.strategy === "credit_gpa")
    return {
      ...base,
      bands,
      fail_grade: d.fail_grade.trim() || "F",
      count_absent_as_attempted: d.count_absent_as_attempted,
    };
  return { ...base, bands, fail_grade: orNull(d.fail_grade) };
}

export const sameConfig = (a: Draft, b: Draft) => JSON.stringify(toConfig(a)) === JSON.stringify(toConfig(b));
