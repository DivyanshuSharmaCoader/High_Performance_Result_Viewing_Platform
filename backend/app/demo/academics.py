"""Synthetic academic structure for the demo tenants (P5.4). Idempotent: existing codes are skipped.

Thapar's course codes follow the public pattern of its catalogue (e.g. UCS301); names and credits are
illustrative. No real student or staff data is used anywhere in the demo (decision D25).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select

from app.core.container import Infra
from app.modules.academics.models import AcademicSession, Cohort, Course, Department, Program, Term


@dataclass(frozen=True)
class Structure:
    sessions: list[tuple[str, str, date, date, bool]]  # code, name, start, end, current
    terms: list[tuple[str, str]]  # code, name — created in every session
    departments: list[tuple[str, str]]
    programs: list[tuple[str, str, str | None, str | None, int | None]]  # code, name, dept code, level, terms
    cohorts: list[tuple[str, str, str]]  # code, name, program code — created in every session
    courses: list[tuple[str, str, str | None, str | None]] = field(
        default_factory=list
    )  # code, name, dept, credits


STRUCTURES: dict[str, Structure] = {
    "thapar": Structure(
        sessions=[
            ("2024-25", "Academic year 2024–25", date(2024, 7, 15), date(2025, 6, 30), False),
            ("2025-26", "Academic year 2025–26", date(2025, 7, 15), date(2026, 6, 30), True),
        ],
        terms=[("ODD", "Odd semester"), ("EVEN", "Even semester")],
        departments=[
            ("CSED", "Computer Science & Engineering"),
            ("ECED", "Electronics & Communication Engineering"),
            ("MED", "Mechanical Engineering"),
            ("SMS", "School of Mathematics"),
        ],
        programs=[
            ("BE-COE", "B.E. Computer Engineering", "CSED", "Undergraduate", 8),
            ("BE-ECE", "B.E. Electronics & Communication", "ECED", "Undergraduate", 8),
            ("BE-MEC", "B.E. Mechanical Engineering", "MED", "Undergraduate", 8),
        ],
        cohorts=[
            ("COE-2A", "COE 2nd year · Group A", "BE-COE"),
            ("COE-2B", "COE 2nd year · Group B", "BE-COE"),
            ("ECE-2A", "ECE 2nd year · Group A", "BE-ECE"),
            ("MEC-2A", "Mechanical 2nd year · Group A", "BE-MEC"),
        ],
        courses=[
            ("UCS301", "Data Structures", "CSED", "4.0"),
            ("UCS310", "Database Management Systems", "CSED", "4.0"),
            ("UCS405", "Discrete Mathematical Structures", "CSED", "3.5"),
            ("UMA035", "Optimization Techniques", "SMS", "3.5"),
            ("UEC301", "Analog Electronic Circuits", "ECED", "4.0"),
            ("UEC310", "Digital Electronics", "ECED", "4.0"),
            ("UME301", "Engineering Thermodynamics", "MED", "4.0"),
            ("UME310", "Strength of Materials", "MED", "4.0"),
            ("UHU005", "Humanities for Engineers", None, "3.0"),
        ],
    ),
    "demoschool": Structure(
        sessions=[("2025-26", "Session 2025–26", date(2025, 4, 1), date(2026, 3, 31), True)],
        terms=[("TERM1", "Term 1"), ("TERM2", "Term 2")],
        departments=[("SEC", "Secondary wing")],
        programs=[
            ("CLASS-8", "Class 8", "SEC", "Middle school", 2),
            ("CLASS-9", "Class 9", "SEC", "Secondary", 2),
            ("CLASS-10", "Class 10", "SEC", "Secondary", 2),
        ],
        cohorts=[
            ("8A", "Class 8 · Section A", "CLASS-8"),
            ("8B", "Class 8 · Section B", "CLASS-8"),
            ("9A", "Class 9 · Section A", "CLASS-9"),
            ("10A", "Class 10 · Section A", "CLASS-10"),
        ],
        courses=[
            ("ENG", "English", None, None),
            ("HIN", "Hindi", None, None),
            ("MATH", "Mathematics", None, None),
            ("SCI", "Science", None, None),
            ("SST", "Social Science", None, None),
        ],
    ),
    "democoaching": Structure(
        sessions=[("2025-26", "Batch year 2025–26", date(2025, 4, 1), date(2026, 3, 31), True)],
        terms=[("PHASE1", "Phase 1"), ("PHASE2", "Phase 2")],
        departments=[("JEE", "Engineering entrance"), ("NEET", "Medical entrance")],
        programs=[
            ("JEE-2027", "JEE Main & Advanced 2027", "JEE", "Two-year classroom", None),
            ("NEET-2027", "NEET 2027", "NEET", "Two-year classroom", None),
        ],
        cohorts=[
            ("JEE-MA", "JEE Morning Batch A", "JEE-2027"),
            ("JEE-EB", "JEE Evening Batch B", "JEE-2027"),
            ("NEET-MA", "NEET Morning Batch A", "NEET-2027"),
        ],
        courses=[
            ("PHY", "Physics", None, None),
            ("CHE", "Chemistry", None, None),
            ("MAT", "Mathematics", "JEE", None),
            ("BIO", "Biology", "NEET", None),
        ],
    ),
}


async def seed_academics(infra: Infra, tenant_id: uuid.UUID, slug: str) -> dict[str, int]:
    spec = STRUCTURES.get(slug)
    if spec is None:
        return {}
    created = {"sessions": 0, "terms": 0, "departments": 0, "programs": 0, "cohorts": 0, "courses": 0}
    async with infra.db.uow(tenant_id) as uow:
        s = uow.session

        async def existing(model: type[Any], **filters: object) -> Any:
            stmt: Select[Any] = select(model)
            for k, v in filters.items():
                stmt = stmt.where(getattr(model, k) == v)
            return (await s.scalars(stmt)).first()

        depts: dict[str, Department] = {}
        for code, name in spec.departments:
            d = await existing(Department, code=code)
            if d is None:
                d = Department(tenant_id=tenant_id, code=code, name=name)
                s.add(d)
                created["departments"] += 1
            depts[code] = d
        await uow.flush()
        progs: dict[str, Program] = {}
        for code, name, dept, level, terms in spec.programs:
            p = await existing(Program, code=code)
            if p is None:
                p = Program(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    department_id=depts[dept].id if dept else None,
                    level=level,
                    duration_terms=terms,
                )
                s.add(p)
                created["programs"] += 1
            progs[code] = p
        for code, name, dept, credits in spec.courses:
            if await existing(Course, code=code) is None:
                s.add(
                    Course(
                        tenant_id=tenant_id,
                        code=code,
                        name=name,
                        department_id=depts[dept].id if dept else None,
                        credits=Decimal(credits) if credits else None,
                    )
                )
                created["courses"] += 1
        await uow.flush()
        for code, name, starts, ends, current in spec.sessions:
            sess = await existing(AcademicSession, code=code)
            if sess is None:
                sess = AcademicSession(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    starts_on=starts,
                    ends_on=ends,
                    is_current=current,
                )
                s.add(sess)
                created["sessions"] += 1
                await uow.flush()
            for i, (tcode, tname) in enumerate(spec.terms, start=1):
                if await existing(Term, session_id=sess.id, code=tcode) is None:
                    s.add(Term(tenant_id=tenant_id, session_id=sess.id, code=tcode, name=tname, sequence=i))
                    created["terms"] += 1
            for ccode, cname, pcode in spec.cohorts:
                if await existing(Cohort, session_id=sess.id, code=ccode) is None:
                    s.add(
                        Cohort(
                            tenant_id=tenant_id,
                            session_id=sess.id,
                            program_id=progs[pcode].id,
                            code=ccode,
                            name=cname,
                        )
                    )
                    created["cohorts"] += 1
            await uow.flush()
    return created
