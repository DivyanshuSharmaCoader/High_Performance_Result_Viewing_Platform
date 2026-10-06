"""Feature and plan catalogue (docs/02 §2, docs/12 §1).

This is the *seed* for the ``features``/``plans``/``plan_features`` tables, synced idempotently by
``scorecode migrate``. At runtime the database is the source of truth (platform admins can edit plans);
code only ever asks the entitlement service about feature *keys*, never about plan codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureDef:
    key: str
    kind: str  # boolean | limit | enum_set
    description: str
    default: Any


class F:
    """Feature keys referenced in code. A test asserts every key exists in the catalogue."""

    MAX_STUDENTS = "max_students"
    MAX_STAFF = "max_staff"
    MAX_ADMINS = "max_admins"
    MAX_STORAGE_MB = "max_storage_mb"
    HISTORY_YEARS = "history_years"
    MAX_PUBLISHED_EXAMS_PER_YEAR = "max_published_exams_per_year"
    MAX_IMPORT_ROWS = "max_import_rows"
    CUSTOM_BRANDING = "custom_branding"
    REMOVE_POWERED_BY = "remove_powered_by"
    CUSTOM_DOMAIN = "custom_domain"
    MULTIPLE_DEPARTMENTS = "multiple_departments"
    MAKER_CHECKER_APPROVAL = "maker_checker_approval"
    SCHEDULED_PUBLICATION = "scheduled_publication"
    EMAIL_NOTIFICATIONS = "email_notifications"
    ADVANCED_ANALYTICS = "advanced_analytics"
    API_ACCESS = "api_access"
    CREDIT_GRADING = "credit_grading"
    VERIFICATION_CHALLENGE = "verification_challenge"
    MARKSHEET_TEMPLATES = "marksheet_templates"


FEATURES: tuple[FeatureDef, ...] = (
    FeatureDef(F.MAX_STUDENTS, "limit", "Active students (not archived/graduated)", 150),
    FeatureDef(F.MAX_STAFF, "limit", "Staff accounts (admins + faculty)", 3),
    FeatureDef(F.MAX_ADMINS, "limit", "Administrator seats within staff", 1),
    FeatureDef(F.MAX_STORAGE_MB, "limit", "File storage (logos, uploads, marksheets)", 1024),
    FeatureDef(F.HISTORY_YEARS, "limit", "Academic years of results kept online", 1),
    FeatureDef(F.MAX_PUBLISHED_EXAMS_PER_YEAR, "limit", "Exam publications per academic year", 4),
    FeatureDef(F.MAX_IMPORT_ROWS, "limit", "Rows per spreadsheet import", 5000),
    FeatureDef(F.CUSTOM_BRANDING, "boolean", "Primary colour, login text and theme tokens", False),
    FeatureDef(F.REMOVE_POWERED_BY, "boolean", "Hide 'Powered by ScoreCode'", False),
    FeatureDef(F.CUSTOM_DOMAIN, "boolean", "Serve the portal on your own domain", False),
    FeatureDef(F.MULTIPLE_DEPARTMENTS, "boolean", "More than one department", False),
    FeatureDef(F.MAKER_CHECKER_APPROVAL, "boolean", "Two-person approval before publishing", False),
    FeatureDef(F.SCHEDULED_PUBLICATION, "boolean", "Publish results automatically at a set time", False),
    FeatureDef(F.EMAIL_NOTIFICATIONS, "boolean", "Email students when results are published", True),
    FeatureDef(F.ADVANCED_ANALYTICS, "boolean", "Trends and cross-exam analytics", False),
    FeatureDef(F.API_ACCESS, "boolean", "Integration API keys", False),
    FeatureDef(F.CREDIT_GRADING, "boolean", "Credit-based grading (SGPA)", True),
    FeatureDef(F.VERIFICATION_CHALLENGE, "boolean", "Full result disclosure after DOB challenge", False),
    FeatureDef(F.MARKSHEET_TEMPLATES, "enum_set", "Marksheet templates available", ["standard"]),
)

UNLIMITED = None


@dataclass(frozen=True, slots=True)
class PlanDef:
    code: str
    name: str
    description: str
    price_paise_yearly: int | None
    sort_order: int
    is_public: bool
    values: dict[str, Any]


PLANS: tuple[PlanDef, ...] = (
    PlanDef(
        "free",
        "Free",
        "Run the full publish flow for a small institution.",
        0,
        10,
        True,
        {
            F.MAX_STUDENTS: 150,
            F.MAX_STAFF: 3,
            F.MAX_ADMINS: 1,
            F.MAX_STORAGE_MB: 1024,
            F.HISTORY_YEARS: 1,
            F.MAX_PUBLISHED_EXAMS_PER_YEAR: 4,
            F.MAX_IMPORT_ROWS: 5000,
        },
    ),
    PlanDef(
        "starter",
        "Starter",
        "For schools and coaching centres up to 600 students.",
        799_900,
        20,
        True,
        {
            F.MAX_STUDENTS: 600,
            F.MAX_STAFF: 15,
            F.MAX_ADMINS: 2,
            F.MAX_STORAGE_MB: 5 * 1024,
            F.HISTORY_YEARS: 3,
            F.MAX_PUBLISHED_EXAMS_PER_YEAR: UNLIMITED,
            F.MAX_IMPORT_ROWS: 20_000,
            F.CUSTOM_BRANDING: True,
        },
    ),
    PlanDef(
        "growth",
        "Growth",
        "Departments, scheduled publication and two-step approval.",
        1_999_900,
        30,
        True,
        {
            F.MAX_STUDENTS: 2000,
            F.MAX_STAFF: 60,
            F.MAX_ADMINS: 5,
            F.MAX_STORAGE_MB: 20 * 1024,
            F.HISTORY_YEARS: 7,
            F.MAX_PUBLISHED_EXAMS_PER_YEAR: UNLIMITED,
            F.MAX_IMPORT_ROWS: 50_000,
            F.CUSTOM_BRANDING: True,
            F.MULTIPLE_DEPARTMENTS: True,
            F.MAKER_CHECKER_APPROVAL: True,
            F.SCHEDULED_PUBLICATION: True,
            F.ADVANCED_ANALYTICS: True,
            F.MARKSHEET_TEMPLATES: ["standard", "classic"],
        },
    ),
    PlanDef(
        "pro",
        "Pro",
        "Custom domain, API access and no ScoreCode branding.",
        4_499_900,
        40,
        True,
        {
            F.MAX_STUDENTS: 5000,
            F.MAX_STAFF: 200,
            F.MAX_ADMINS: 15,
            F.MAX_STORAGE_MB: 100 * 1024,
            F.HISTORY_YEARS: UNLIMITED,
            F.MAX_PUBLISHED_EXAMS_PER_YEAR: UNLIMITED,
            F.MAX_IMPORT_ROWS: 50_000,
            F.CUSTOM_BRANDING: True,
            F.REMOVE_POWERED_BY: True,
            F.CUSTOM_DOMAIN: True,
            F.MULTIPLE_DEPARTMENTS: True,
            F.MAKER_CHECKER_APPROVAL: True,
            F.SCHEDULED_PUBLICATION: True,
            F.ADVANCED_ANALYTICS: True,
            F.API_ACCESS: True,
            F.VERIFICATION_CHALLENGE: True,
            F.MARKSHEET_TEMPLATES: ["standard", "classic"],
        },
    ),
    PlanDef(
        "enterprise",
        "Enterprise",
        "Contract plan; limits are set per institution.",
        None,
        50,
        False,
        {
            F.MAX_STUDENTS: UNLIMITED,
            F.MAX_STAFF: UNLIMITED,
            F.MAX_ADMINS: UNLIMITED,
            F.MAX_STORAGE_MB: UNLIMITED,
            F.HISTORY_YEARS: UNLIMITED,
            F.MAX_PUBLISHED_EXAMS_PER_YEAR: UNLIMITED,
            F.MAX_IMPORT_ROWS: 50_000,
            F.CUSTOM_BRANDING: True,
            F.REMOVE_POWERED_BY: True,
            F.CUSTOM_DOMAIN: True,
            F.MULTIPLE_DEPARTMENTS: True,
            F.MAKER_CHECKER_APPROVAL: True,
            F.SCHEDULED_PUBLICATION: True,
            F.ADVANCED_ANALYTICS: True,
            F.API_ACCESS: True,
            F.VERIFICATION_CHALLENGE: True,
            F.MARKSHEET_TEMPLATES: ["standard", "classic"],
        },
    ),
)

FREE_PLAN_CODE = "free"  # the fallback when a subscription lapses (docs/12 §1) — used only here.
LIMIT_TO_USAGE_METRIC = {
    F.MAX_STUDENTS: "active_students",
    F.MAX_STAFF: "staff_users",
    F.MAX_ADMINS: "admin_users",
    F.MAX_STORAGE_MB: "storage_bytes",
    F.MAX_PUBLISHED_EXAMS_PER_YEAR: "published_exams_year",
}
