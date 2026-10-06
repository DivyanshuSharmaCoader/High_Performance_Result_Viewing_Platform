"""Staff accounts (admins and faculty): invite, role changes, disable/enable, ownership transfer.

Seat limits (``max_staff``, ``max_admins``) are enforced through the entitlement service inside the
same transaction; disabled accounts release their seats.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, NotFound, PermissionDenied, ValidationFailed
from app.core.http import Principal
from app.core.tenant import TenantContext
from app.modules.academics.models import Department
from app.modules.audit.service import Actor, diff, record
from app.modules.directory.models import StaffProfile
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.identity.models import User, UserRole
from app.modules.identity.service import AuthService

ROLE_LABELS = {
    "institution_owner": "Owner",
    "institution_admin": "Administrator",
    "faculty": "Faculty",
}
INVITABLE_ROLES = ("institution_admin", "faculty")
ADMIN_ROLES = ("institution_owner", "institution_admin")


@dataclass
class StaffMember:
    id: uuid.UUID
    full_name: str
    email: str | None
    role: str
    status: str
    last_login_at: datetime | None
    created_at: datetime
    employee_code: str | None = None
    designation: str | None = None
    department_id: uuid.UUID | None = None
    phone: str | None = None


@dataclass
class ProfileData:
    full_name: str
    employee_code: str | None
    designation: str | None
    department_id: uuid.UUID | None
    phone: str | None


def _blank_to_none(value: str | None) -> str | None:
    cleaned = " ".join((value or "").split())
    return cleaned or None


class StaffService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra
        self.ent = EntitlementService(infra)

    async def _role_of(self, uow: UnitOfWork, user_id: uuid.UUID) -> str | None:
        roles = (await uow.session.scalars(select(UserRole.role).where(UserRole.user_id == user_id))).all()
        for r in ("institution_owner", "institution_admin", "faculty"):
            if r in roles:
                return r
        return None

    async def _get_staff(self, uow: UnitOfWork, user_id: uuid.UUID, *, lock: bool = False) -> User:
        stmt = select(User).where(User.id == user_id, User.kind == "staff")
        if lock:
            stmt = stmt.with_for_update()
        user = (await uow.session.scalars(stmt)).one_or_none()
        if user is None:
            raise NotFound("Staff member not found")
        return user

    async def list(
        self, uow: UnitOfWork, *, q: str | None = None, role: str | None = None
    ) -> list[StaffMember]:
        stmt = (
            select(User, UserRole.role, StaffProfile)
            .join(UserRole, (UserRole.user_id == User.id) & (UserRole.tenant_id == User.tenant_id))
            .outerjoin(StaffProfile, StaffProfile.user_id == User.id)
            .where(User.kind == "staff")
            .order_by(User.full_name, User.id)
        )
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
        if role:
            stmt = stmt.where(UserRole.role == role)
        rows = (await uow.session.execute(stmt)).all()
        return [_member(u, r, p) for u, r, p in rows]

    async def get(self, uow: UnitOfWork, user_id: uuid.UUID) -> StaffMember:
        user = await self._get_staff(uow, user_id)
        role = await self._role_of(uow, user.id) or "faculty"
        profile = (
            await uow.session.scalars(select(StaffProfile).where(StaffProfile.user_id == user.id))
        ).one_or_none()
        return _member(user, role, profile)

    async def update_profile(
        self, uow: UnitOfWork, principal: Principal, user_id: uuid.UUID, data: ProfileData
    ) -> StaffMember:
        user = await self._get_staff(uow, user_id, lock=True)
        full_name = " ".join(data.full_name.split())
        if len(full_name) < 2:
            raise ValidationFailed("Enter the person's full name.", field="full_name")
        if data.department_id is not None:
            dept = (
                await uow.session.scalars(select(Department).where(Department.id == data.department_id))
            ).one_or_none()
            if dept is None:
                raise ValidationFailed("That department doesn't exist.", field="department_id")
            if dept.archived_at is not None:
                raise ValidationFailed("That department is archived.", field="department_id")
        profile = (
            await uow.session.scalars(
                select(StaffProfile).where(StaffProfile.user_id == user.id).with_for_update()
            )
        ).one_or_none()
        if profile is None:
            profile = StaffProfile(tenant_id=user.tenant_id, user_id=user.id)
            uow.session.add(profile)
        fields = ("employee_code", "designation", "department_id", "phone")
        before = {"full_name": user.full_name, **{f: getattr(profile, f, None) for f in fields}}
        user.full_name = full_name
        profile.employee_code = _blank_to_none(data.employee_code)
        profile.designation = _blank_to_none(data.designation)
        profile.department_id = data.department_id
        profile.phone = _blank_to_none(data.phone)
        await uow.flush()
        after = {"full_name": user.full_name, **{f: getattr(profile, f) for f in fields}}
        d_before, d_after = diff(before, after)
        if d_after:
            await record(
                uow,
                Actor.from_principal(principal),
                "user.profile_updated",
                entity_type="user",
                entity_id=user.id,
                summary=f"Updated {user.full_name}'s profile",
                before=d_before,
                after=d_after,
            )
        return await self.get(uow, user.id)

    async def invite(
        self,
        uow: UnitOfWork,
        tenant: TenantContext,
        principal: Principal,
        *,
        email: str,
        full_name: str,
        role: str,
    ) -> User:
        if role not in INVITABLE_ROLES:
            raise ValidationFailed("Choose Administrator or Faculty.", field="role")
        email = email.strip().lower()
        exists = (await uow.session.scalars(select(User.id).where(func.lower(User.email) == email))).first()
        if exists is not None:
            raise Conflict("Someone with this email already has an account here.", field="email")
        await self.ent.consume(uow, F.MAX_STAFF, 1)
        if role in ADMIN_ROLES:
            await self.ent.consume(uow, F.MAX_ADMINS, 1)
        user = User(
            tenant_id=tenant.tenant_id,
            kind="staff",
            login_id=email,
            email=email,
            full_name=full_name.strip(),
            status="invited",
        )
        uow.session.add(user)
        await uow.flush()
        uow.session.add(UserRole(tenant_id=tenant.tenant_id, user_id=user.id, role=role))
        await AuthService(self.infra).issue_invite(
            uow, tenant, user, ROLE_LABELS[role], principal.display_name
        )
        await record(
            uow,
            Actor.from_principal(principal),
            "user.invited",
            entity_type="user",
            entity_id=user.id,
            summary=f"Invited {full_name.strip()} as {ROLE_LABELS[role]}",
            after={"email": email, "role": role},
        )
        return user

    async def resend_invite(
        self, uow: UnitOfWork, tenant: TenantContext, principal: Principal, user_id: uuid.UUID
    ) -> None:
        user = await self._get_staff(uow, user_id)
        if user.status != "invited":
            raise InvalidState("This person has already accepted their invitation.")
        role = await self._role_of(uow, user.id) or "faculty"
        await AuthService(self.infra).issue_invite(
            uow, tenant, user, ROLE_LABELS[role], principal.display_name
        )
        await record(
            uow, Actor.from_principal(principal), "user.invite_resent", entity_type="user", entity_id=user.id
        )

    async def change_role(self, uow: UnitOfWork, principal: Principal, user_id: uuid.UUID, role: str) -> None:
        if role not in INVITABLE_ROLES:
            raise ValidationFailed("Choose Administrator or Faculty.", field="role")
        if user_id == principal.user_id:
            raise PermissionDenied("You can't change your own role.")
        user = await self._get_staff(uow, user_id, lock=True)
        current = await self._role_of(uow, user.id)
        if current == "institution_owner":
            raise PermissionDenied("Transfer ownership before changing the owner's role.")
        if current == role:
            return
        if role in ADMIN_ROLES and user.status != "disabled":
            await self.ent.consume(uow, F.MAX_ADMINS, 1)
        if current in ADMIN_ROLES and user.status != "disabled":
            await self.ent.release(uow, F.MAX_ADMINS, 1)
        await uow.session.execute(
            delete(UserRole).where(UserRole.user_id == user.id, UserRole.role != "student")
        )
        uow.session.add(UserRole(tenant_id=user.tenant_id, user_id=user.id, role=role))
        await AuthService(self.infra).sessions.revoke_all_for_user(
            uow, user.id
        )  # privilege change → new session
        await record(
            uow,
            Actor.from_principal(principal),
            "user.role_changed",
            entity_type="user",
            entity_id=user.id,
            before={"role": current},
            after={"role": role},
        )

    async def set_disabled(
        self, uow: UnitOfWork, principal: Principal, user_id: uuid.UUID, disabled: bool
    ) -> None:
        if user_id == principal.user_id:
            raise PermissionDenied("You can't disable your own account.")
        user = await self._get_staff(uow, user_id, lock=True)
        role = await self._role_of(uow, user.id)
        if role == "institution_owner":
            raise PermissionDenied("The owner account can't be disabled. Transfer ownership first.")
        if disabled and user.status == "disabled":
            return
        if not disabled and user.status != "disabled":
            return
        if disabled:
            await self.ent.release(uow, F.MAX_STAFF, 1)
            if role in ADMIN_ROLES:
                await self.ent.release(uow, F.MAX_ADMINS, 1)
            before = user.status
            user.status = "disabled"
            await AuthService(self.infra).sessions.revoke_all_for_user(uow, user.id)
        else:
            await self.ent.consume(uow, F.MAX_STAFF, 1)
            if role in ADMIN_ROLES:
                await self.ent.consume(uow, F.MAX_ADMINS, 1)
            before = user.status
            user.status = "active" if user.password_hash else "invited"
        await record(
            uow,
            Actor.from_principal(principal),
            "user.disabled" if disabled else "user.enabled",
            entity_type="user",
            entity_id=user.id,
            before={"status": before},
            after={"status": user.status},
        )

    async def transfer_ownership(self, uow: UnitOfWork, principal: Principal, target_id: uuid.UUID) -> None:
        if "institution_owner" not in principal.roles:
            raise PermissionDenied("Only the owner can transfer ownership.")
        if target_id == principal.user_id:
            raise ValidationFailed("Choose another administrator.")
        target = await self._get_staff(uow, target_id, lock=True)
        if target.status != "active" or await self._role_of(uow, target.id) != "institution_admin":
            raise InvalidState("Ownership can only be transferred to an active administrator.")
        await uow.session.execute(
            delete(UserRole).where(
                UserRole.user_id.in_([principal.user_id, target.id]), UserRole.role != "student"
            )
        )
        uow.session.add(UserRole(tenant_id=target.tenant_id, user_id=target.id, role="institution_owner"))
        uow.session.add(
            UserRole(tenant_id=target.tenant_id, user_id=principal.user_id, role="institution_admin")
        )
        sessions = AuthService(self.infra).sessions
        await sessions.revoke_all_for_user(uow, target.id)
        await sessions.revoke_all_for_user(uow, principal.user_id, except_hash=principal.session_hash)
        current_hash = principal.session_hash
        uow.after_commit(lambda: sessions.invalidate_tenant_sessions_cache([current_hash]))
        await record(
            uow,
            Actor.from_principal(principal),
            "tenant.ownership_transferred",
            entity_type="user",
            entity_id=target.id,
            before={"owner": str(principal.user_id)},
            after={"owner": str(target.id)},
        )


def _member(user: User, role: str, profile: StaffProfile | None) -> StaffMember:
    return StaffMember(
        user.id,
        user.full_name,
        user.email,
        role,
        user.status,
        user.last_login_at,
        user.created_at,
        employee_code=profile.employee_code if profile else None,
        designation=profile.designation if profile else None,
        department_id=profile.department_id if profile else None,
        phone=profile.phone if profile else None,
    )
