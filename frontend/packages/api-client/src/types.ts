import type { components } from "./schema";

/** Response/request types generated from backend/openapi.json (regenerate with `make openapi`). */
export type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];
export type SessionOut = Schemas["SessionOut"];
export type Staff = Schemas["StaffOut"];
export type BrandingOut = Schemas["BrandingOut"];
export type SettingsOut = Schemas["SettingsOut"];
export type SubscriptionOut = Schemas["SubscriptionOut"];
export type TrialOut = Schemas["TrialOut"];
export type TrialState = TrialOut["state"];
export type PlanCatalogue = Schemas["PlanCatalogue"];
export type PublicPlan = Schemas["PublicPlan"];
export type AuditEntry = Schemas["AuditEntry"];
export type JobOut = Schemas["JobOut"];
export type TenantRow = Schemas["TenantRow"];
export type PlatformMe = Schemas["PlatformMeOut"];

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
  total?: number | null;
}

export interface TenantConfig {
  tenant: { slug: string; name: string };
  branding: {
    display_name: string;
    short_name: string | null;
    logo_url: string | null;
    logo_version: number;
    login_heading: string | null;
    login_message: string | null;
    footer_text: string | null;
    support_email: string | null;
    show_powered_by: boolean;
    tokens: {
      primary: string;
      primary_contrast: string;
      primary_ink: string;
      accent: string;
      accent_contrast: string;
      font_family: string;
    };
  };
  settings: { student_activation_mode: string; locale: string };
  features: Record<string, unknown>;
}
export type Onboarding = Schemas["OnboardingOut"];
export type OnboardingStep = Schemas["OnboardingStep"];
export type LimitUsage = Schemas["LimitUsage"];

// ---- Platform console (responses typed loosely server-side as dicts) ------------------------------
export interface TenantList {
  items: TenantRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface TenantDetail {
  id: string;
  slug: string;
  name: string;
  type: string;
  status: string;
  status_reason: string | null;
  timezone: string;
  created_at: string;
  host: string;
  official_name: string;
  contact_email: string | null;
  current_plan: string | null;
  subscriptions: {
    id: string;
    plan_code: string;
    plan_name: string;
    status: string;
    period_start: string;
    period_end: string | null;
    billing_ref: string | null;
    created_at: string;
  }[];
  overrides: { feature_key: string; value: unknown; reason: string; expires_at: string | null }[];
  usage: Record<string, number>;
  trial: {
    status: "active" | "ended" | "converted" | "revoked";
    started_at: string;
    ends_at: string;
    ended_at: string | null;
    end_reason: string | null;
    risk_score: number;
    flags: string[];
    granted: boolean;
  } | null;
  users: { staff: number; students: number };
  last_activity_at: string | null;
}

export interface PlansCatalog {
  plans: {
    code: string;
    name: string;
    description: string;
    price_paise_yearly: number | null;
    is_public: boolean;
    active: boolean;
    values: Record<string, unknown>;
  }[];
  features: { key: string; kind: "boolean" | "limit" | "enum_set"; description: string }[];
}

export interface PlatformOverview {
  tenants: { by_status: Record<string, number>; by_plan: Record<string, number>; new_last_7_days: number };
  users: { active_students: number; staff: number };
  queues: { queue: string; status: string; count: number; oldest_seconds: number }[];
  publications: { last_7_days: number; live: number };
  process_metrics: {
    scope: string;
    redis_cache_hit_rate: number | null;
    requests_total: number;
    errors_5xx: number;
    p95_upper_bound_ms_by_route_class: Record<string, number | null>;
  };
}

export interface DeepHealth {
  checks: { name: string; status: string; latency_ms: number; error?: string; circuit_breaker?: string }[];
  checked_at: string;
}

export type PlatformAuditEntry = Schemas["PlatformAuditEntry"];

// ---- Academic structure ----------------------------------------------------------------------------
export type AcademicSession = Schemas["AcademicSessionOut"];
export type Term = Schemas["TermOut"];
export type Department = Schemas["DepartmentOut"];
export type Program = Schemas["ProgramOut"];
export type Cohort = Schemas["CohortOut"];
export type Course = Schemas["CourseOut"];
export type CourseList = Schemas["CourseList"];
export type StructureCounts = Schemas["StructureCounts"];

// ---- Directory & imports ---------------------------------------------------------------------------
export type Student = Schemas["StudentOut"];
export type StudentPage = Schemas["Page_StudentOut_"];
export type StudentCounts = Schemas["StudentCountsOut"];
export type StudentStatus = Student["status"];
export type AccountState = Student["account"];
export type Membership = Schemas["MembershipOut"];
export type CohortMembersResult = Schemas["CohortMembersOut"];
export type ActivationCodes = Schemas["ActivationCodesOut"];
export type IssuedCode = Schemas["IssuedCodeOut"];
export type ImportJob = Schemas["ImportOut"];
export type ImportListItem = Schemas["ImportListItem"];
export type ImportStatus = ImportJob["status"];
export type ImportField = Schemas["FieldOut"];
export type ImportIssue = Schemas["IssueOut"];
export type ImportRow = Schemas["RowOut"];
export type ImportRowsPage = Schemas["RowsPage"];

// ---- Grading ----------------------------------------------------------------------------------------
export type GradingScheme = Schemas["SchemeOut"];
export type GradingSchemeDetail = Schemas["SchemeDetailOut"];
export type GradingTemplate = Schemas["TemplateOut"];
export type GradingStrategy = GradingScheme["strategy"];
export type GradePreview = Schemas["ExamResultOut"];
export type PaperPreview = Schemas["PaperResultOut"];

// ---- Examinations -----------------------------------------------------------------------------------
export type Exam = Schemas["ExamOut"];
export type ExamListItem = Schemas["ExamListItem"];
export type ExamStatus = Exam["status"];
export type ExamKind = Exam["kind"];
export type ExamPaper = Schemas["ExamPaperOut"];
export type ExamComponent = Schemas["ExamComponentOut"];
export type ExamCohort = Schemas["ExamCohortOut"];
export type ExamAction = Schemas["ExamActionOut"];

// ---- Marks ------------------------------------------------------------------------------------------
export type MarkSheet = Schemas["SheetOut"];
export type MarkSheetStudent = Schemas["SheetStudentOut"];
export type MarkEntry = Schemas["EntryOut"];
export type SavedMark = Schemas["SavedEntryOut"];
export type MarkingWork = Schemas["WorkItemOut"];
export type Attendance = MarkEntry["attendance"];

// ---- Results ----------------------------------------------------------------------------------------
export type ResultsOverview = Schemas["ResultsOverviewOut"];
export type ResultRun = Schemas["ResultRunOut"];
export type ResultRunStatus = ResultRun["status"];
export type ResultApproval = Schemas["ResultApprovalOut"];
export type ResultStudent = Schemas["ResultStudentOut"];
export type ResultPaper = Schemas["ResultPaperOut"];
export type ResultStudentsPage = Schemas["ResultStudentsPage"];
export type ResultOutcome = ResultStudent["outcome"];

// ---- Student results (published snapshots) ----------------------------------------------------------
export type ResultPayload = Schemas["ResultPayload"];
export type SnapPaper = Schemas["SnapPaper"];
export type SnapResult = Schemas["SnapResult"];
export type MyResult = Schemas["MyResultOut"];
export type MyResultItem = Schemas["MyResultItem"];
export type MyStats = Schemas["MyStatsOut"];
export type Publication = Schemas["PublicationOut"];
