"""Array-bound membership predicates (app/core/sql.py) at import scale, against real Postgres.

The sizes are past the limits the plain forms hit: 40,000 values exceed asyncpg's 32,767 bind parameters, and
20,000 row values exhaust Postgres's stack when written as ``(a, b) IN ((..), ..)``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.sql import in_rows, in_values
from app.modules.directory.models import CohortMembership, Student
from tests.helpers import make_structure, make_student, make_tenant

pytestmark = pytest.mark.integration


async def test_in_values_and_in_rows_match_exactly_at_import_scale(infra) -> None:
    t = await make_tenant(infra, plan="enterprise")
    s = await make_structure(infra, t)
    a = await make_student(infra, t, enrollment_no="KEEP1", cohort_id=s.cohort_id)
    b = await make_student(infra, t, enrollment_no="KEEP2", cohort_id=s.cohort_id)
    await make_student(infra, t, enrollment_no="OTHER", cohort_id=s.cohort_id)

    noise = [f"N{i:06}" for i in range(40_000)]
    pairs = [(uuid.uuid4(), uuid.uuid4()) for _ in range(20_000)]
    async with infra.db.uow(t.id) as uow:
        found = await uow.session.scalars(
            select(Student.enrollment_no)
            .where(in_values(Student.enrollment_no, [*noise, "KEEP1", "KEEP2"]))
            .with_for_update()  # as the import commit locks them
        )
        assert sorted(found) == ["KEEP1", "KEEP2"]

        members = await uow.session.scalars(
            select(CohortMembership.student_id).where(
                in_rows(
                    (CohortMembership.student_id, CohortMembership.cohort_id),
                    [*pairs, (a, s.cohort_id), (b, uuid.uuid4())],
                )
            )
        )
        assert list(members) == [a]  # both columns must match, not each one separately

        assert list(await uow.session.scalars(select(Student.id).where(in_values(Student.id, [])))) == []
        assert (
            list(
                await uow.session.scalars(
                    select(CohortMembership.student_id).where(
                        in_rows((CohortMembership.student_id, CohortMembership.cohort_id), [])
                    )
                )
            )
            == []
        )
