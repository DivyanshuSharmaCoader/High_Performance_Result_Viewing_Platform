"""Migration helpers that make the isolation rules impossible to forget (docs/06 §2, P2.6).

* ``enable_tenant_rls(table)`` — ENABLE + FORCE RLS and a fail-closed ``tenant_isolation`` policy.
* ``grant_app(table, ...)`` — explicit, minimal grants for the runtime role (no blanket defaults).
* ``grant_platform(table, ...)`` — grants for the platform (BYPASSRLS) role.

The CI test ``tests/integration/test_rls_coverage.py`` asserts every table with ``tenant_id`` has RLS
enabled, forced and a policy, and that ``scorecode_app`` holds no UPDATE/DELETE on append-only tables.
"""

from __future__ import annotations

from alembic import op

APP_ROLE = "scorecode_app"
PLATFORM_ROLE = "scorecode_platform"
MIGRATOR_ROLE = "scorecode_migrator"

# Fail closed: current_setting() WITHOUT missing_ok raises if app.tenant_id was never set.
TENANT_PREDICATE = "tenant_id = current_setting('app.tenant_id')::uuid"


def enable_tenant_rls(table: str, *, predicate: str = TENANT_PREDICATE) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})")


def allow_definer_access(table: str) -> None:
    """Let SECURITY DEFINER functions (owned by the migrator role) read across tenants.

    Only used for the handful of tables that must be read before a tenant context exists
    (host resolution, job claiming, public verification). The runtime role never gains this.
    """
    op.execute(f"CREATE POLICY definer_access ON {table} TO {MIGRATOR_ROLE} USING (true) WITH CHECK (true)")


def grant_app(table: str, privileges: str = "SELECT, INSERT, UPDATE, DELETE") -> None:
    op.execute(f"GRANT {privileges} ON {table} TO {APP_ROLE}")


def grant_platform(table: str, privileges: str = "SELECT") -> None:
    op.execute(f"GRANT {privileges} ON {table} TO {PLATFORM_ROLE}")


def drop_policies(table: str, *names: str) -> None:
    for name in names or ("tenant_isolation",):
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
