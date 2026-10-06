"""Synthetic students for the demo tenants (P6). Deterministic and idempotent: the same names and
enrollment numbers every run; existing enrollment numbers are skipped. Names are generated from common
first names and surnames — no real student data is used (decision D25).

The first student of each tenant gets an activated account with the demo password, so the student
portal can be shown without printing activation slips.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.core.container import Infra
from app.modules.academics.models import AcademicSession, Cohort
from app.modules.directory.models import Student
from app.modules.directory.service import StudentData, StudentService
from app.modules.identity.models import User, UserRole

FIRST = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Arjun",
    "Reyansh",
    "Sai",
    "Krishna",
    "Ishaan",
    "Kabir",
    "Rohan",
    "Dhruv",
    "Ayaan",
    "Vihaan",
    "Atharv",
    "Arnav",
    "Ananya",
    "Diya",
    "Saanvi",
    "Aadhya",
    "Ira",
    "Myra",
    "Kiara",
    "Anika",
    "Navya",
    "Riya",
    "Sara",
    "Meera",
    "Tara",
    "Zoya",
    "Nisha",
    "Pooja",
    "Kavya",
    "Simran",
    "Harleen",
    "Gurleen",
    "Manav",
    "Yash",
    "Nikhil",
    "Farhan",
    "Imran",
    "Joseph",
    "Maria",
    "Neha",
    "Shreya",
    "Tanvi",
    "Varun",
]
LAST = [
    "Sharma",
    "Verma",
    "Gupta",
    "Singh",
    "Kaur",
    "Gill",
    "Sandhu",
    "Malhotra",
    "Mehta",
    "Iyer",
    "Nair",
    "Menon",
    "Reddy",
    "Rao",
    "Das",
    "Banerjee",
    "Chatterjee",
    "Mukherjee",
    "Patel",
    "Shah",
    "Joshi",
    "Kulkarni",
    "Deshmukh",
    "Khan",
    "Qureshi",
    "Fernandes",
    "D'Souza",
    "Thomas",
    "Bhatia",
    "Arora",
]


@dataclass(frozen=True)
class RosterSpec:
    enrollment: str  # format string with {cohort} (1-based) and {n} (1-based)
    admission_year: int | None


ROSTERS = {
    "thapar": RosterSpec("10240{cohort}{n:03d}", 2024),
    "demoschool": RosterSpec("DPS25{cohort}{n:02d}", 2025),
    "democoaching": RosterSpec("DCA25{cohort}{n:03d}", 2025),
}


def demo_student_login(slug: str) -> str | None:
    spec = ROSTERS.get(slug)
    return spec.enrollment.format(cohort=1, n=1) if spec else None


async def seed_students(infra: Infra, tenant_id: uuid.UUID, slug: str, count: int, password_hash: str) -> int:
    spec = ROSTERS.get(slug)
    if spec is None or count <= 0:
        return 0
    rng = random.Random(f"{slug}-students")  # noqa: S311 - demo data, not security
    created = 0
    async with infra.db.uow(tenant_id) as uow:
        current = (
            await uow.session.scalars(select(AcademicSession).where(AcademicSession.is_current.is_(True)))
        ).one_or_none()
        if current is None:
            return 0
        cohorts = list(
            (
                await uow.session.scalars(
                    select(Cohort).where(Cohort.session_id == current.id).order_by(Cohort.code)
                )
            ).all()
        )
        if not cohorts:
            return 0
        existing = set((await uow.session.scalars(select(Student.enrollment_no))).all())
        service = StudentService(infra)
        per_cohort = max(1, count // len(cohorts))
        first_student: Student | None = None
        for ci, cohort in enumerate(cohorts, start=1):
            for n in range(1, per_cohort + 1):
                first, last = rng.choice(FIRST), rng.choice(LAST)
                enrollment = spec.enrollment.format(cohort=ci, n=n)
                if enrollment in existing:
                    continue
                student = await service.create(
                    uow,
                    None,
                    StudentData(
                        enrollment_no=enrollment,
                        full_name=f"{first} {last}",
                        email=f"{first.lower()}.{enrollment.lower()}@students.{slug}.example.com",
                        admission_year=spec.admission_year,
                    ),
                    cohort_ids=[cohort.id],
                    audit=False,
                )
                created += 1
                if ci == 1 and n == 1:
                    first_student = student
        if first_student is not None and first_student.user_id is None:
            user = User(
                tenant_id=tenant_id,
                kind="student",
                login_id=first_student.enrollment_no,
                email=first_student.email,
                full_name=first_student.full_name,
                password_hash=password_hash,
                status="active",
            )
            uow.session.add(user)
            await uow.flush()
            uow.session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role="student"))
            first_student.user_id = user.id
    return created
