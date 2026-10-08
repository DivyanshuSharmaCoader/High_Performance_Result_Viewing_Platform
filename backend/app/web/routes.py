"""Router registry: every module's HTTP surface is mounted here (and nowhere else)."""

from __future__ import annotations

from fastapi import FastAPI

from app.modules.academics.router import router as academics_router
from app.modules.audit.router import router as audit_router
from app.modules.branding.router import router as branding_router
from app.modules.directory.router import router as students_router
from app.modules.documents.router import admin_router as marksheets_admin_router
from app.modules.documents.router import student_router as my_marksheets_router
from app.modules.entitlements.router import router as plans_router
from app.modules.examinations.router import router as exams_router
from app.modules.grading.router import router as grading_router
from app.modules.identity.router import platform_router as platform_auth_router
from app.modules.identity.router import router as identity_router
from app.modules.identity.staff_router import router as staff_router
from app.modules.ingestion.router import router as imports_router
from app.modules.marks.router import router as marks_router
from app.modules.notifications.router import router as notifications_router
from app.modules.platform.router import router as platform_router
from app.modules.publishing.router import admin_router as publications_router
from app.modules.publishing.router import student_router as my_results_router
from app.modules.results.router import router as results_router
from app.modules.tenancy.router import router as settings_router
from app.modules.tenancy.signup_router import router as signup_router
from app.modules.verification.router import router as verification_router
from app.web.jobs_router import router as jobs_router


def include_routers(app: FastAPI) -> None:
    # Requests are matched against the routers in this order, each testing its routes' patterns, so the
    # student read path (config, me, results, marksheets, inbox, verify) goes first: on result day it is
    # nearly all traffic. Route matching was 6% of API CPU under scenario B with these near the end
    # (benchmarks/results/2026-10-09-read-path.md).
    for router in (
        identity_router,
        branding_router,
        my_results_router,
        my_marksheets_router,
        notifications_router,
        verification_router,
        platform_auth_router,
        staff_router,
        settings_router,
        signup_router,
        audit_router,
        jobs_router,
        platform_router,
        academics_router,
        students_router,
        imports_router,
        grading_router,
        exams_router,
        marks_router,
        results_router,
        publications_router,
        marksheets_admin_router,
        plans_router,
    ):
        app.include_router(router)
