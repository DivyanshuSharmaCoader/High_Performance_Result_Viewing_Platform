# Architecture Decision Records

Short records of decisions that shape the code. Format: context → decision → consequences. The full
decision register (including business decisions) is in [18 §3](../18-risks-and-decisions.md#3-decision-register--confirm-before-writing-production-code).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith, one image with `api`/`worker` modes | Accepted |
| [0002](0002-shared-schema-rls.md) | Shared schema + `tenant_id` + composite FKs + forced, fail-closed RLS | Accepted |
| [0003](0003-tenant-scoped-users.md) | Users belong to exactly one tenant | Accepted |
| [0004](0004-host-based-tenancy.md) | Host-based tenant routing in every environment | Accepted |
| [0005](0005-opaque-sessions.md) | Opaque server-side sessions, host-only cookies, double-submit CSRF | Accepted |
| [0006](0006-student-activation-codes.md) | Student activation codes, no DOB passwords | Accepted |
| [0007](0007-uuidv7.md) | UUIDv7 primary keys generated in the app | Accepted |
| [0008](0008-job-queue.md) | In-house PostgreSQL `SKIP LOCKED` job queue behind SECURITY DEFINER functions | Accepted |
| [0009](0009-dev-object-storage.md) | SeaweedFS as the S3-compatible store in development | Accepted |
| [0010](0010-module-boundaries.md) | How module boundaries are enforced in practice | Accepted |
