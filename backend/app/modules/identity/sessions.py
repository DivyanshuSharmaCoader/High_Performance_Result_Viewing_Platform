"""Opaque server-side sessions (decision D5, docs/10 §2).

* 256-bit random token in a host-only HttpOnly cookie; the DB stores only SHA-256(token).
* Sessions are bound to a tenant: lookups run under the host tenant's RLS context, so a cookie
  replayed on another tenant's host simply isn't found (→ 401).
* Validation is cached briefly (Redis + a 10 s local tier); revocation deletes the cache entry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.http import Principal
from app.core.security import hash_token, new_token
from app.modules.identity.models import PlatformSession, PlatformUser, Session, User, UserRole
from app.modules.identity.permissions import PLATFORM_ROLE_PERMISSIONS, permissions_for

SESSION_LOCAL_TTL_S = 10
SLIDE_AFTER = timedelta(minutes=5)


def _cache_key(session_hash: bytes) -> str:
    return "sess:" + session_hash.hex()


def _platform_cache_key(session_hash: bytes) -> str:
    return "psess:" + session_hash.hex()


class SessionService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra
        self.settings = infra.settings

    # ---- lifetimes ------------------------------------------------------------------------------
    def lifetimes(self, user_kind: str, now: datetime) -> tuple[datetime, datetime]:
        s = self.settings
        if user_kind == "student":
            return now + timedelta(days=s.student_session_days), now + timedelta(
                days=s.student_session_days * 3
            )
        return now + timedelta(hours=s.staff_session_idle_hours), now + timedelta(
            days=s.staff_session_absolute_days
        )

    def cookie_max_age(self, user_kind: str) -> int:
        s = self.settings
        if user_kind == "student":
            return s.student_session_days * 86400
        return s.staff_session_absolute_days * 86400

    # ---- tenant sessions ------------------------------------------------------------------------
    async def create(self, uow: UnitOfWork, user: User, *, ip: str | None, user_agent: str | None) -> str:
        token = new_token(32)
        now = utcnow()
        expires, absolute = self.lifetimes(user.kind, now)
        uow.session.add(
            Session(
                id=hash_token(token),
                tenant_id=user.tenant_id,
                user_id=user.id,
                created_at=now,
                last_seen_at=now,
                expires_at=expires,
                absolute_expires_at=absolute,
                reauthenticated_at=now,
                ip=ip,
                user_agent=(user_agent or "")[:300] or None,
            )
        )
        return token

    async def load(self, tenant_id: uuid.UUID, token: str) -> Principal | None:
        session_hash = hash_token(token)
        key = _cache_key(session_hash)
        data: dict[str, Any] | None = await self.infra.cache.get(key, local_ttl_s=SESSION_LOCAL_TTL_S)
        now = utcnow()
        if data is None or data.get("tenant_id") != str(tenant_id):
            data = await self._load_from_db(tenant_id, session_hash, now)
            if data is None:
                return None
            ttl = int(min(60, max(1, (datetime.fromisoformat(data["expires_at"]) - now).total_seconds())))
            await self.infra.cache.set(key, data, ttl, local_ttl_s=SESSION_LOCAL_TTL_S)
        if data["tenant_id"] != str(tenant_id):
            return None
        if now >= datetime.fromisoformat(data["expires_at"]) or now >= datetime.fromisoformat(
            data["absolute_expires_at"]
        ):
            return None
        roles = frozenset(data["roles"])
        reauth = data.get("reauthenticated_at")
        return Principal(
            kind="user",
            user_id=uuid.UUID(data["user_id"]),
            tenant_id=uuid.UUID(data["tenant_id"]),
            roles=roles,
            permissions=permissions_for(roles),
            session_hash=session_hash,
            user_kind=data["user_kind"],
            display_name=data["name"],
            reauthenticated_at=datetime.fromisoformat(reauth) if reauth else None,
        )

    async def _load_from_db(
        self, tenant_id: uuid.UUID, session_hash: bytes, now: datetime
    ) -> dict[str, Any] | None:
        async with self.infra.db.uow(tenant_id) as uow:
            row = (
                await uow.session.execute(
                    select(Session, User)
                    .join(User, (User.id == Session.user_id) & (User.tenant_id == Session.tenant_id))
                    .where(Session.id == session_hash)
                )
            ).one_or_none()
            if row is None:
                return None
            sess, user = row
            if sess.revoked_at is not None or user.status != "active":
                return None
            if now >= sess.expires_at or now >= sess.absolute_expires_at:
                return None
            roles = (
                await uow.session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))
            ).all()
            if now - sess.last_seen_at > SLIDE_AFTER:
                new_expiry, _ = self.lifetimes(user.kind, now)
                sess.last_seen_at = now
                sess.expires_at = min(new_expiry, sess.absolute_expires_at)
            return {
                "user_id": str(user.id),
                "tenant_id": str(tenant_id),
                "roles": sorted(roles),
                "user_kind": user.kind,
                "name": user.full_name,
                "expires_at": sess.expires_at.isoformat(),
                "absolute_expires_at": sess.absolute_expires_at.isoformat(),
                "reauthenticated_at": sess.reauthenticated_at.isoformat()
                if sess.reauthenticated_at
                else None,
            }

    async def mark_reauthenticated(self, uow: UnitOfWork, session_hash: bytes) -> None:
        await uow.session.execute(
            update(Session).where(Session.id == session_hash).values(reauthenticated_at=utcnow())
        )
        uow.after_commit(lambda: self.infra.cache.delete(_cache_key(session_hash)))

    async def revoke(self, uow: UnitOfWork, session_hash: bytes) -> None:
        await uow.session.execute(
            update(Session).where(Session.id == session_hash).values(revoked_at=utcnow())
        )
        uow.after_commit(lambda: self.infra.cache.delete(_cache_key(session_hash)))

    async def revoke_all_for_user(
        self, uow: UnitOfWork, user_id: uuid.UUID, *, except_hash: bytes | None = None
    ) -> int:
        stmt = select(Session.id).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        hashes = list((await uow.session.scalars(stmt)).all())
        hashes = [h for h in hashes if h != except_hash]
        if hashes:
            await uow.session.execute(
                update(Session).where(Session.id.in_(hashes)).values(revoked_at=utcnow())
            )
            keys = [_cache_key(h) for h in hashes]
            uow.after_commit(lambda: self.infra.cache.delete(*keys))
        return len(hashes)

    async def list_for_user(self, uow: UnitOfWork, user_id: uuid.UUID) -> list[Session]:
        now = utcnow()
        rows = await uow.session.scalars(
            select(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None), Session.expires_at > now)
            .order_by(Session.last_seen_at.desc())
        )
        return list(rows.all())

    async def purge_expired(self, uow: UnitOfWork, older_than: datetime) -> int:
        result = await uow.session.execute(
            delete(Session).where((Session.expires_at < older_than) | (Session.revoked_at < older_than))
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # ---- platform sessions ----------------------------------------------------------------------
    async def create_platform(
        self, uow: UnitOfWork, user: PlatformUser, *, ip: str | None, user_agent: str | None
    ) -> str:
        token = new_token(32)
        now = utcnow()
        uow.session.add(
            PlatformSession(
                id=hash_token(token),
                platform_user_id=user.id,
                totp_verified=True,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=self.settings.platform_session_hours),
                ip=ip,
                user_agent=(user_agent or "")[:300] or None,
            )
        )
        return token

    async def load_platform(self, token: str) -> Principal | None:
        session_hash = hash_token(token)
        key = _platform_cache_key(session_hash)
        data: dict[str, Any] | None = await self.infra.cache.get(key, local_ttl_s=SESSION_LOCAL_TTL_S)
        now = utcnow()
        if data is None:
            async with self.infra.db.platform_uow() as uow:
                row = (
                    await uow.session.execute(
                        select(PlatformSession, PlatformUser)
                        .join(PlatformUser, PlatformUser.id == PlatformSession.platform_user_id)
                        .where(PlatformSession.id == session_hash)
                    )
                ).one_or_none()
                if row is None:
                    return None
                sess, user = row
                if (
                    sess.revoked_at
                    or not sess.totp_verified
                    or user.status != "active"
                    or now >= sess.expires_at
                ):
                    return None
                data = {
                    "user_id": str(user.id),
                    "role": user.role,
                    "name": user.full_name,
                    "expires_at": sess.expires_at.isoformat(),
                }
            await self.infra.cache.set(key, data, 60, local_ttl_s=SESSION_LOCAL_TTL_S)
        if now >= datetime.fromisoformat(data["expires_at"]):
            return None
        return Principal(
            kind="platform",
            user_id=uuid.UUID(data["user_id"]),
            tenant_id=None,
            roles=frozenset({data["role"]}),
            permissions=PLATFORM_ROLE_PERMISSIONS.get(data["role"], frozenset()),
            session_hash=session_hash,
            user_kind="platform",
            display_name=data["name"],
        )

    async def revoke_platform(self, uow: UnitOfWork, session_hash: bytes) -> None:
        await uow.session.execute(
            update(PlatformSession).where(PlatformSession.id == session_hash).values(revoked_at=utcnow())
        )
        uow.after_commit(lambda: self.infra.cache.delete(_platform_cache_key(session_hash)))

    async def invalidate_tenant_sessions_cache(self, session_hashes: list[bytes]) -> None:
        if session_hashes:
            await self.infra.cache.delete(*[_cache_key(h) for h in session_hashes])
