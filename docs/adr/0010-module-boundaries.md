# ADR 0010 — Module boundaries in practice

**Decision.** Enforced by `import-linter` in CI: (1) `app.core` never imports `app.modules`; (2) the grading engine (`app.modules.grading.engine`) is pure — no database, framework or I/O imports. Within `app.modules`, modules call each other's *service functions*; a module's tables are written only by that module's services (reviewed in code review rather than linted, because SQLAlchemy relationships and read-side joins make a strict "api-package only" rule impractical without duplicating DTOs everywhere).

**Consequences.** The two boundaries that protect correctness (pure grading) and layering (kernel) are machine-checked; the rest is convention documented in docs/08 §2.
