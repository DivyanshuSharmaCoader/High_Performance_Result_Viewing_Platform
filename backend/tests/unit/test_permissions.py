"""Permission matrix snapshot: changing who may do what must be a deliberate, reviewed change.

If this fails after an intentional change, regenerate ``permission_matrix.json`` and explain the change
in the PR description.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.identity.permissions import PLATFORM_ROLE_PERMISSIONS, ROLE_PERMISSIONS, P, permissions_for

SNAPSHOT = Path(__file__).with_name("permission_matrix.json")


def test_permission_matrix_matches_snapshot() -> None:
    current = {k: sorted(v) for k, v in {**ROLE_PERMISSIONS, **PLATFORM_ROLE_PERMISSIONS}.items()}
    assert current == json.loads(SNAPSHOT.read_text())


def test_students_hold_only_self_service_permissions() -> None:
    assert permissions_for(["student"]) == {P.ME_RESULTS, P.NOTIFICATIONS_SELF}


def test_faculty_cannot_approve_publish_or_manage_people() -> None:
    faculty = permissions_for(["faculty"])
    for forbidden in (
        P.RESULTS_APPROVE,
        P.PUBLICATIONS_MANAGE,
        P.STAFF_MANAGE,
        P.STUDENTS_MANAGE,
        P.SETTINGS_MANAGE,
    ):
        assert forbidden not in faculty


def test_only_owner_can_transfer_ownership() -> None:
    assert P.OWNER_TRANSFER in permissions_for(["institution_owner"])
    assert P.OWNER_TRANSFER not in permissions_for(["institution_admin"])


def test_unknown_roles_grant_nothing() -> None:
    assert permissions_for(["superuser", "platform_admin"]) == frozenset()
