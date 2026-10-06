# ADR 0001 — Modular monolith

**Context.** A 1–3 person team building a multi-tenant SaaS whose critical operations (publish = snapshot + verification + notifications) span several domains and must be atomic. Tenant isolation must be enforced in one place.

**Decision.** One Python package (`backend/app`) with bounded-context modules under `app/modules/*`, a shared kernel in `app/core`, and one Docker image that runs as `scorecode api` or `scorecode worker`.

**Consequences.** Cross-module operations are single ACID transactions. Scaling is by running more API/worker containers. Modules that later need a different scaling profile (PDF rendering, verification) can be extracted because they communicate through service functions and jobs, not shared tables. See [docs/08 §1](../08-backend-architecture.md#1-style-modular-monolith).
