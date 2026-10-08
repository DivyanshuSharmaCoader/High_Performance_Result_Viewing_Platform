"""Public verification records (docs/10 §10, docs/07 §2.7).

One record per published result, keyed by a **global** random code: 128 bits from the OS CSPRNG,
Crockford base32 (26 characters), never derived from a student, exam or tenant. The code is printed on
the marksheet as a QR code and as text.

The public status is **derived**, not stored: it follows the publication (published → valid, superseded,
withdrawn; scheduled or cancelled → not issued) unless this one record was revoked. A withdrawal is then
one row update, and the two can never disagree. Only revocation, and the aggregate lookup counter, are
written here after creation (column-level grants).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped

CODE_PATTERN = "^[0-9A-HJKMNP-TV-Z]{26}$"


class VerificationRecord(TenantScoped, Base):
    __tablename__ = "verification_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "publication_id", "student_id", name="uq_verification_records__result"),
        ForeignKeyConstraint(
            ["tenant_id", "publication_id", "student_id"],
            [
                "published_results.tenant_id",
                "published_results.publication_id",
                "published_results.student_id",
            ],
            ondelete="RESTRICT",
            name="fk_verification_records__published_results",
        ),
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code"),
        CheckConstraint("(revoked_at IS NULL) = (revoked_reason IS NULL)", name="revocation"),
        CheckConstraint("verify_count >= 0", name="verify_count"),
    )

    code: Mapped[str] = mapped_column(String(26), primary_key=True)
    publication_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    revoked_at: Mapped[datetime | None]
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    revoked_by: Mapped[uuid.UUID | None]
    verify_count: Mapped[int] = mapped_column(Integer, server_default="0")
    last_verified_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
