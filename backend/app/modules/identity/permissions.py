"""Role → permission mapping. Code, not data (docs/07 §2.3): fixed roles are easier to reason about,
test and audit. A snapshot test pins this matrix so changes are deliberate."""

from __future__ import annotations

from collections.abc import Iterable


class P:
    """Permission names (single source of truth)."""

    SETTINGS_MANAGE = "settings.manage"
    BRANDING_MANAGE = "branding.manage"
    SUBSCRIPTION_VIEW = "subscription.view"
    SUBSCRIPTION_MANAGE = "subscription.manage"  # start the trial; owner only
    OWNER_TRANSFER = "owner.transfer"
    DATA_EXPORT = "data.export"  # every record of the institution, as a download; owner only (P18.5)
    STAFF_VIEW = "staff.view"
    STAFF_MANAGE = "staff.manage"
    STUDENTS_VIEW = "students.view"
    STUDENTS_MANAGE = "students.manage"
    ACADEMICS_VIEW = "academics.view"
    ACADEMICS_MANAGE = "academics.manage"
    GRADING_VIEW = "grading.view"
    GRADING_MANAGE = "grading.manage"
    EXAMS_VIEW = "exams.view"
    EXAMS_MANAGE = "exams.manage"
    EXAMS_VIEW_ASSIGNED = "exams.view_assigned"
    MARKS_ENTER_ALL = "marks.enter_all"
    MARKS_ENTER_ASSIGNED = "marks.enter_assigned"
    PAPERS_SUBMIT_ASSIGNED = "papers.submit_assigned"
    PAPERS_REVIEW = "papers.review"
    IMPORTS_MANAGE = "imports.manage"
    IMPORTS_MARKS_ASSIGNED = "imports.marks_assigned"
    RESULTS_PROCESS = "results.process"
    RESULTS_APPROVE = "results.approve"
    RESULTS_VIEW = "results.view"
    PUBLICATIONS_MANAGE = "publications.manage"
    ANALYTICS_VIEW = "analytics.view"
    STATS_VIEW_ASSIGNED = "stats.view_assigned"
    AUDIT_VIEW = "audit.view"
    JOBS_VIEW = "jobs.view"
    ME_RESULTS = "me.results"
    NOTIFICATIONS_SELF = "notifications.self"
    ACCOUNT_MFA = "account.mfa"  # two-step sign-in for one's own staff account


class PlatformP:
    TENANTS_VIEW = "platform.tenants.view"
    TENANTS_MANAGE = "platform.tenants.manage"
    PLANS_MANAGE = "platform.plans.manage"
    HEALTH_VIEW = "platform.health.view"
    AUDIT_VIEW = "platform.audit.view"


_ADMIN = frozenset(
    {
        P.SETTINGS_MANAGE,
        P.BRANDING_MANAGE,
        P.SUBSCRIPTION_VIEW,
        P.STAFF_VIEW,
        P.STAFF_MANAGE,
        P.STUDENTS_VIEW,
        P.STUDENTS_MANAGE,
        P.ACADEMICS_VIEW,
        P.ACADEMICS_MANAGE,
        P.GRADING_VIEW,
        P.GRADING_MANAGE,
        P.EXAMS_VIEW,
        P.EXAMS_MANAGE,
        P.EXAMS_VIEW_ASSIGNED,
        P.MARKS_ENTER_ALL,
        P.PAPERS_REVIEW,
        P.IMPORTS_MANAGE,
        P.RESULTS_PROCESS,
        P.RESULTS_APPROVE,
        P.RESULTS_VIEW,
        P.PUBLICATIONS_MANAGE,
        P.ANALYTICS_VIEW,
        P.AUDIT_VIEW,
        P.JOBS_VIEW,
        P.NOTIFICATIONS_SELF,
        P.ACCOUNT_MFA,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "institution_owner": _ADMIN | {P.OWNER_TRANSFER, P.SUBSCRIPTION_MANAGE, P.DATA_EXPORT},
    "institution_admin": _ADMIN,
    "faculty": frozenset(
        {
            P.EXAMS_VIEW_ASSIGNED,
            P.MARKS_ENTER_ASSIGNED,
            P.PAPERS_SUBMIT_ASSIGNED,
            P.IMPORTS_MARKS_ASSIGNED,
            P.STATS_VIEW_ASSIGNED,
            P.JOBS_VIEW,
            P.NOTIFICATIONS_SELF,
            P.ACCOUNT_MFA,
        }
    ),
    "student": frozenset({P.ME_RESULTS, P.NOTIFICATIONS_SELF}),
}

PLATFORM_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "platform_admin": frozenset(
        {
            PlatformP.TENANTS_VIEW,
            PlatformP.TENANTS_MANAGE,
            PlatformP.PLANS_MANAGE,
            PlatformP.HEALTH_VIEW,
            PlatformP.AUDIT_VIEW,
        }
    ),
    "support": frozenset({PlatformP.TENANTS_VIEW, PlatformP.HEALTH_VIEW, PlatformP.AUDIT_VIEW}),
    "readonly": frozenset({PlatformP.TENANTS_VIEW, PlatformP.HEALTH_VIEW}),
}

STAFF_ROLES = ("institution_owner", "institution_admin", "faculty")
ADMIN_ROLES = ("institution_owner", "institution_admin")


def permissions_for(roles: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for role in roles:
        out |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(out)
