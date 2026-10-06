"""auth_tokens: allow the post-sign-up sign-in handoff purpose

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_auth_tokens__purpose"), "auth_tokens", type_="check")
    op.create_check_constraint(
        "purpose",
        "auth_tokens",
        "purpose IN ('invite', 'password_reset', 'activation', 'email_verification', 'signin_handoff')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_auth_tokens__purpose"), "auth_tokens", type_="check")
    op.create_check_constraint(
        "purpose", "auth_tokens", "purpose IN ('invite', 'password_reset', 'activation', 'email_verification')"
    )
