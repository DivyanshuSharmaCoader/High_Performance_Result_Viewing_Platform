# 07 · Database Architecture

> Covers brief section **I** and §21. Visual ER diagram: [diagrams/er-diagram.md](diagrams/er-diagram.md). Isolation rationale: [06 Multi-tenancy](06-multi-tenancy.md).

Database: **PostgreSQL 16+** (managed in production). One database, one schema (`public`), shared tables with `tenant_id`.

---

## 1. Global conventions

| Convention | Rule | Why |
|---|---|---|
| Primary keys | `id uuid` generated in the app as **UUIDv7** | Time-ordered (good B-tree locality, unlike v4), non-enumerable, can be generated before insert (useful for idempotency & batch inserts). |
| Tenant key | `tenant_id uuid NOT NULL` on every tenant-owned table, plus `UNIQUE (tenant_id, id)` | Enables composite FKs and RLS ([06](06-multi-tenancy.md)). |
| Foreign keys | Composite `(tenant_id, x_id) → parent(tenant_id, id)` | Cross-tenant references are impossible. |
| Timestamps | `created_at`, `updated_at timestamptz NOT NULL DEFAULT now()` | Always UTC in DB; tenant timezone applied in presentation. |
| Actor columns | `created_by uuid` (user id) where meaningful | Fast "who" without joining audit. Audit log is the full record. |
| Optimistic locking | `version int NOT NULL DEFAULT 1` on concurrently edited rows (mark entries, exams, settings) | Prevents lost updates; API uses `If-Match`/version field. |
| Enumerations | `text` + `CHECK (status IN (...))` rather than PG `ENUM` | Adding a value is a simple migration; no enum-alter locking quirks. |
| Money | `bigint` paise | No floating point. |
| Marks | `numeric(7,2)` | Exact decimal (half marks are common); never float. |
| Flexible-but-validated data | `jsonb` only where the shape is tenant-configurable (exam components, grading bands, published snapshot); validated by Pydantic schemas before write | Avoids EAV tables while keeping one place of validation. |
| Deletion | See §6 — **RESTRICT by default**; academic records never hard-deleted while tenant exists | Correctness & audit. |
| Naming | `snake_case`, plural table names, `ix_<table>__<cols>`, `uq_...`, `fk_...`, `ck_...` | Predictable migrations. |
| Migrations | Alembic, forward-only in production, every migration reviewed; expand → migrate → contract for breaking changes | Zero-downtime deploys. |

---

## 2. Entity catalogue

Legend: 🌐 = global (no tenant_id, no RLS) · 🏫 = tenant-owned (tenant_id + RLS)

### 2.1 Platform & commercial
| Table | Kind | Purpose | Key columns |
|---|---|---|---|
| `plans` | 🌐 | Plan catalogue (Free, Starter, Growth, Pro, Enterprise) | `id`, `code` UQ, `name`, `is_public`, `price_paise_yearly`, `sort_order`, `active` |
| `features` | 🌐 | Feature/limit catalogue | `key` PK (e.g. `max_students`, `custom_domain`), `kind` (`boolean`/`limit`), `description`, `default_value jsonb` |
| `plan_features` | 🌐 | Value of each feature for each plan | PK `(plan_id, feature_key)`, `value jsonb` (`true`, `600`, `null` = unlimited) |
| `tenants` | 🌐* | The institution | `id`, `slug` UQ, `name`, `type` (`school`/`college`/`university`/`coaching`/`other`), `status` (`pending`/`active`/`suspended`/`closing`/`closed`), `timezone`, `created_at` |
| `tenant_domains` | 🏫 | Subdomain aliases & custom domains | `domain` UQ (global), `tenant_id`, `kind` (`custom`), `status`, `verification_token`, `verified_at` |
| `tenant_subscriptions` | 🏫 | Current & past subscriptions | `tenant_id`, `plan_id`, `status` (`trialing`/`active`/`past_due`/`cancelled`/`expired`), `period_start`, `period_end`, `billing_ref`; partial UQ: one `active`/`trialing` row per tenant |
| `tenant_feature_overrides` | 🏫 | Per-tenant exceptions (Enterprise deals, temporary boosts) | `tenant_id`, `feature_key`, `value jsonb`, `reason`, `expires_at`, `created_by_platform_user`; UQ `(tenant_id, feature_key)` |
| `tenant_usage_counters` | 🏫 | Live counters for limited resources (row-locked during limit checks) | PK `(tenant_id, metric)` (`active_students`, `staff_users`, `storage_bytes`), `value bigint`, `updated_at`; reconciled nightly against real counts |
| `tenant_usage_daily` | 🏫 | Daily metered usage snapshot | PK `(tenant_id, day, metric)`, `value bigint` |
| `platform_users` | 🌐 | ScoreCode staff | `id`, `email` UQ, `password_hash`, `totp_secret_enc`, `role` (`platform_admin`/`support`/`readonly`), `status` |
| `platform_audit_logs` | 🌐 | Actions by platform staff | like `audit_logs` without tenant scoping (but with optional `target_tenant_id`) |

\* `tenants` is read through a dedicated resolver (by host) before tenant context exists; the app role has `SELECT` on minimal columns only. RLS on `tenants` restricts the app role to `id = app.tenant_id` once context is set.

### 2.2 Tenant configuration
| Table | Purpose | Notes |
|---|---|---|
| `tenant_settings` | 1:1 typed settings | `approval_mode` (`single`/`maker_checker`), `student_activation_mode`, `verification_disclosure` (`masked`/`masked_plus_challenge`), `default_grading_scheme_id`, `locale`, `publish_notify_email bool` |
| `tenant_branding` | 1:1 branding | `display_name`, `logo_file_id`, `favicon_file_id`, `primary_color`, `secondary_color` (validated hex + contrast check), `font_family` (from allow-list), `login_heading`, `login_message`, `footer_text`, `support_email`, `show_powered_by bool` |
| `marksheet_templates` | 🌐 + 🏫 | Global templates (tenant_id NULL, no RLS on those rows via policy `tenant_id IS NULL OR tenant_id = ctx`) and tenant-specific | `code`, `name`, `engine_version`, `html_template` (sandboxed Jinja), `css`, `params_schema jsonb` |
| `notification_templates` | Tenant overrides of default templates | `event` (`result_published`…), `channel`, `subject`, `body` |

### 2.3 Identity & access
| Table | Purpose | Key constraints |
|---|---|---|
| `users` | Every tenant login (staff and students) | `UQ (tenant_id, lower(email))` where email not null; `UQ (tenant_id, login_id)` (login_id = email for staff, enrollment no. for students); `password_hash` (Argon2id, nullable until activated); `status` (`invited`/`active`/`disabled`); `kind` (`staff`/`student`); `last_login_at`; `failed_login_count`, `locked_until` |
| `user_roles` | Role grants | PK `(tenant_id, user_id, role)`; `role` CHECK in (`institution_owner`, `institution_admin`, `faculty`, `student`); optional `department_id` scope (V1) |
| `sessions` | Server-side sessions | `id` = SHA-256 of the random token (token itself never stored); `user_id`, `tenant_id`, `created_at`, `last_seen_at`, `expires_at`, `ip`, `user_agent`, `revoked_at`; index `(user_id)` for "log out everywhere" |
| `auth_tokens` | One-time tokens: email verification, invite, password reset, student activation | `token_hash` UQ, `purpose`, `user_id`, `expires_at`, `consumed_at` |
| `api_keys` (V1) | Integration keys | `prefix` (shown), `key_hash`, `scopes text[]`, `expires_at`, `last_used_at`, `revoked_at` |

Roles → permissions mapping is **code** (`identity/permissions.py`), e.g. `faculty` → `{marks.enter_assigned, paper.submit_assigned, stats.view_assigned}`. Reason: fixed roles are easier to reason about, test, and audit; DB-defined custom roles are an Enterprise feature later.

### 2.4 Academic structure & directory
| Table | Purpose | Key constraints / indexes |
|---|---|---|
| `academic_sessions` | e.g. "2025-26" | `UQ (tenant_id, code)`; `starts_on < ends_on` CHECK; `is_current` (partial UQ: one current per tenant) |
| `terms` | Semester/term within a session | FK session; `UQ (tenant_id, session_id, code)`; `sequence` |
| `departments` | Optional grouping | `UQ (tenant_id, code)`; `archived_at` |
| `programs` | Class/degree/course-of-study | FK department (nullable); `UQ (tenant_id, code)`; `level` (free text), `duration_terms` |
| `cohorts` | Section/batch/group within a program for a session | FK program, FK session; `UQ (tenant_id, session_id, code)` |
| `courses` | Subject catalogue | `UQ (tenant_id, code)`; `credits numeric(4,1)` nullable; FK department nullable; `archived_at` |
| `students` | Student master record | `UQ (tenant_id, enrollment_no)`; `user_id` UQ nullable (account created on activation); `full_name`, `date_of_birth` (nullable, for verification challenge), `email`, `phone`, `guardian_name`, `admission_year`, `status` (`active`/`graduated`/`withdrawn`/`archived`); index `(tenant_id, status)` for entitlement counting; trigram index on name for admin search |
| `cohort_memberships` | Student ∈ cohort (per session) | PK `(tenant_id, cohort_id, student_id)`; index `(tenant_id, student_id)`; a student in one cohort per program per session enforced by UQ `(tenant_id, student_id, session_id, program_id)` (denormalised columns) |
| `staff_profiles` | Extra info for staff users | PK `(tenant_id, user_id)`; `employee_code`, `designation`, `department_id` |

### 2.5 Examinations & grading
| Table | Purpose | Key constraints |
|---|---|---|
| `grading_schemes` | Named scheme | `UQ (tenant_id, name)`; `strategy` (`percentage_bands`/`credit_gpa`/`marks_only`) |
| `grading_scheme_versions` | Immutable versions | `UQ (tenant_id, scheme_id, version)`; `config jsonb` (bands, grade points, pass rules, rounding); never updated after first use |
| `examinations` | An exam event | FK term; `name`, `kind`; `status` (state machine — see [state diagrams](diagrams/state-diagrams.md)); `grading_scheme_version_id` (pinned at processing); `scheduled_publish_at`; `version` |
| `exam_cohorts` | Which cohorts sit the exam | PK `(tenant_id, exam_id, cohort_id)` |
| `exam_papers` | Course × exam with components | `UQ (tenant_id, exam_id, course_id)`; `components jsonb` e.g. `[{"code":"INT","label":"Internal","max":40},{"code":"EXT","label":"External","max":60,"min_pass":21}]`; `max_total numeric`; `pass_total numeric`; `credits` (copied from course at creation — historical stability) |
| `paper_assignments` | Faculty allowed to enter marks | PK `(tenant_id, exam_paper_id, cohort_id, user_id)` |
| `paper_submissions` | Workflow state per paper × cohort | PK `(tenant_id, exam_paper_id, cohort_id)`; `status` (`open`/`submitted`/`returned`/`locked`); `submitted_by`, `submitted_at` |

### 2.6 Marks & ingestion
| Table | Purpose | Key constraints |
|---|---|---|
| `mark_entries` | One row per student × paper | `UQ (tenant_id, exam_paper_id, student_id)`; `components jsonb` (`{"INT": 35, "EXT": 50.5}`); `total numeric(7,2)` (computed in app, checked `>= 0`); `attendance` (`present`/`absent`/`exempt`/`malpractice`/`withheld`); `version`; `updated_by`, `source` (`grid`/`import:<job_id>`); index `(tenant_id, exam_paper_id)` |
| `files` | Every uploaded/generated file | `object_key` UQ, `kind`, `content_type`, `size_bytes`, `sha256`, `uploaded_by`, `scan_status` |
| `import_jobs` | One upload + its lifecycle | `kind` (`marks`/`students`/`courses`…); `target_exam_id` nullable; `file_id`; `mapping jsonb`; `status` (`uploaded`/`parsing`/`validated`/`committing`/`committed`/`failed`/`cancelled`); counts (`rows_total`, `rows_valid`, `rows_warning`, `rows_error`); `file_sha256` + partial UQ `(tenant_id, target_exam_id, file_sha256)` among non-cancelled jobs to catch duplicate uploads |
| `import_rows` | Staging rows | PK `(tenant_id, import_job_id, row_no)`; `raw jsonb`, `normalized jsonb`, `issues jsonb` (`[{"col":"EXT","code":"OUT_OF_RANGE","severity":"error","msg":"..."}]`), `status`; deleted 30 days after commit (retention job) |

### 2.7 Results, publication, documents, verification
| Table | Purpose | Key constraints |
|---|---|---|
| `result_runs` | One processing run | FK exam; `revision int`; `grading_scheme_version_id`; `input_hash` (hash of all inputs), `content_hash` (hash of all outputs); `status` (`running`/`completed`/`failed`/`stale`/`approved`/`published`); `started_by`; `override` (reason + unsubmitted papers, when processed early); `stats`/`anomalies` jsonb for the preview; UQ `(tenant_id, exam_id, revision)`; partial UQ: one `running` run per exam |
| `student_exam_results` | Working computed result (summary) | UQ `(tenant_id, result_run_id, student_id)`; `total`, `max_total`, `percentage`, `grade`, `grade_point`, `sgpa`, `credits_earned`, `outcome` (`pass`/`fail`/`absent`/`withheld`/`incomplete`), `rank` nullable |
| `student_paper_results` | Working computed result per paper | UQ `(tenant_id, result_run_id, student_id, exam_paper_id)`; `total`, `grade`, `grade_point`, `passed bool` — normalized for analytics SQL |
| `approvals` | Approval decisions | FK result_run; `decision` (`approved`/`rejected`/`revoked`); `decided_by`; `content_hash`; `comment`; append-only (app role: SELECT, INSERT). Maker ≠ checker is enforced in the service when the tenant uses maker-checker mode (a DB trigger is not built) |
| `publications` | A published version of an exam's results | UQ `(tenant_id, exam_id, version)`; FK `result_run_id`; `status` (`scheduled`/`published`/`superseded`/`withdrawn`); `scheduled_at`, `published_at`, `withdrawn_at`, `withdraw_reason`, `supersedes_id`; partial UQ: at most one `published` per exam |
| `published_results` | **Immutable read model** — exactly what a student sees | PK `(tenant_id, publication_id, student_id)`; `payload jsonb` (student, exam, papers, totals, grade, remarks, institution display data); `payload_hash`; `marksheet_file_id`; **covering index** `(tenant_id, student_id, published_at DESC) INCLUDE (publication_id, exam_id)` for "latest"/"history" queries. App role has no `UPDATE` grant except the status flags handled via `publications` |
| `exam_statistics` | Immutable stats snapshot per publication | PK `(tenant_id, publication_id)`; `stats jsonb` |
| `marksheet_documents` | PDF render state | PK = composite FK `(tenant_id, publication_id, student_id)` → `published_results`; `status` (`pending`/`rendered`/`failed`; rendered ⇒ file + sha256); `file_id` (kind `marksheet`); `sha256` hex; `template_code`, `template_version`; `attempts`, `last_error` (exception type only). Created with the publication, never deleted. App: SELECT, INSERT, UPDATE |
| `verification_records` | Public verification | `code` **PK, global** (128-bit random, Crockford base32, 26 chars, not derived from anything); `tenant_id`; UQ + composite FK `(tenant_id, publication_id, student_id)`; `revoked_at`/`revoked_reason`/`revoked_by`; `verify_count`, `last_verified_at`. **Status is derived, not stored** (as built, P11.4): it follows the publication (published → valid; superseded; withdrawn; scheduled/cancelled → not issued) unless the record is revoked — so a withdrawal is one row update and the two can't disagree; the document hash is read from `marksheet_documents`. App: SELECT, INSERT and column-level UPDATE of the counter and revocation only. Read on the verify host through the SECURITY DEFINER function `verification_lookup(code) → (tenant_id, tenant_status)`, then under that tenant's RLS |

### 2.8 Notifications, audit, jobs
| Table | Purpose | Key constraints |
|---|---|---|
| `notifications` | In-app inbox | index `(tenant_id, user_id, created_at DESC)`, partial index on unread |
| `notification_deliveries` | Per-channel delivery | `channel` (`email`/`sms`/`whatsapp`), `status`, `provider_message_id`, `attempts`, `last_error` |
| `audit_logs` | Append-only audit trail | `id`, `tenant_id`, `occurred_at`, `actor_type` (`user`/`platform_user`/`system`/`api_key`), `actor_id`, `action` (`marks.updated`), `entity_type`, `entity_id`, `before jsonb`, `after jsonb` (diff), `request_id`, `ip`, `user_agent`, `prev_hash`/`hash` (V1 hash chain). **Range-partitioned by month**; index `(tenant_id, occurred_at DESC)`, `(tenant_id, entity_type, entity_id)`. App role: `INSERT` + `SELECT` only — no `UPDATE`/`DELETE`. |
| `jobs` (queue library tables) | Background jobs | Managed by the queue library; each job payload includes `tenant_id` |
| `idempotency_keys` | Safe retries of POSTs | PK `(tenant_id, key)`, `request_hash`, `response jsonb`, `expires_at` |

---

## 3. Relationship summary

```
tenants 1─* users 1─* user_roles
tenants 1─1 tenant_settings, tenant_branding
tenants 1─* tenant_subscriptions *─1 plans 1─* plan_features *─1 features
academic_sessions 1─* terms 1─* examinations
departments 1─* programs 1─* cohorts *─1 academic_sessions
cohorts 1─* cohort_memberships *─1 students (0..1─1 users)
examinations 1─* exam_papers *─1 courses
examinations *─* cohorts (exam_cohorts)
exam_papers 1─* mark_entries *─1 students
exam_papers 1─* paper_assignments *─1 users(faculty)
import_jobs 1─* import_rows ; import_jobs *─1 files
examinations 1─* result_runs 1─* student_exam_results 1─* student_paper_results
result_runs 1─* approvals
examinations 1─* publications 1─* published_results 1─1 verification_records
published_results 1─0..1 marksheet_documents ─1 files
publications 1─1 exam_statistics
users 1─* notifications 1─* notification_deliveries
```

---

## 4. Critical constraints (correctness lives in the database too)

1. **Composite tenant FKs** on every reference (cross-tenant impossible).
2. `UQ (tenant_id, enrollment_no)` — no duplicate students.
3. `UQ (tenant_id, exam_paper_id, student_id)` on `mark_entries` — one mark row per student per paper (imports *upsert*).
4. `CHECK (total >= 0)`; component values validated in app against `exam_papers.components` (DB can't easily validate dynamic JSON ranges — a trigger can be added if needed; app validation is mandatory and tested).
5. Partial unique `publications (tenant_id, exam_id) WHERE status = 'published'` — exactly one live version.
6. `grading_scheme_versions` immutable after use: trigger raises on `UPDATE` when referenced by a `result_run`.
7. `published_results` immutable: no `UPDATE`/`DELETE` grant to app role; trigger guard as a second layer.
8. `audit_logs` append-only: no `UPDATE`/`DELETE` grant.
9. One active subscription per tenant: partial unique index on `tenant_subscriptions (tenant_id) WHERE status IN ('active','trialing')`.
10. `verification_records.code` globally unique, random.
11. Entitlement-limited inserts (students, staff) check limits **in the same transaction** after `SELECT ... FOR UPDATE` on the tenant's `tenant_usage_counters` row (or an advisory lock keyed by tenant) to avoid race conditions where two parallel imports both pass the check ([12](12-entitlements.md)).

---

## 5. Indexing strategy

Rule: **every index must be justified by a query in the API spec**; verify with `EXPLAIN (ANALYZE, BUFFERS)` in the performance phase. All tenant-owned indexes lead with `tenant_id`.

| Query (hot path first) | Index |
|---|---|
| Student: latest result / history | `published_results (tenant_id, student_id, published_at DESC) INCLUDE (publication_id, exam_id)` |
| Student: one result | PK `(tenant_id, publication_id, student_id)` |
| Session lookup on every request | PK `sessions(id)` (hash) |
| Host → tenant | `tenants(slug)` UQ, `tenant_domains(domain)` UQ |
| Verification | `verification_records(code)` UQ |
| Notifications inbox | `(tenant_id, user_id, created_at DESC)`; partial `WHERE read_at IS NULL` |
| Marks grid for a paper | `mark_entries (tenant_id, exam_paper_id)` |
| Faculty: my assignments | `paper_assignments (tenant_id, user_id)` |
| Admin student search | `students (tenant_id, enrollment_no)` UQ; `pg_trgm` GIN on `full_name` |
| Entitlement counting | `students (tenant_id) WHERE status = 'active'` (partial) — or maintained counter |
| Audit viewer | `audit_logs (tenant_id, occurred_at DESC)`, `(tenant_id, entity_type, entity_id)` |
| Import errors view | `import_rows (tenant_id, import_job_id, status)` |

Avoid: indexes on low-cardinality columns alone; GIN on whole `jsonb` payloads (we never query inside snapshots).

---

## 6. Cascade and deletion strategy

| Data | Deletion behaviour |
|---|---|
| Tenant | **Never cascades.** Offboarding job deletes tenant data table-by-table in dependency order after grace period, logs a platform audit event, leaves verification codes returning "institution closed". |
| Students, staff, courses, departments, programs | **Soft archive** (`archived_at`/`status`). Hard delete only if never referenced (e.g. created by mistake), checked by FK RESTRICT. |
| Exams | Hard delete allowed only in `draft` with no marks (FK RESTRICT stops otherwise); children `exam_papers`, `exam_cohorts` `ON DELETE CASCADE` from exam (owned composition). |
| Mark entries | Editable until exam approval; never deleted after publication (corrections create new values + audit). |
| Import jobs → import rows | `ON DELETE CASCADE` (staging data owned by job); rows purged after retention. |
| Result runs | Superseded runs kept (audit/compare); purge old *unpublished* runs after 1 year. |
| Publications / published results / verification | **Never deleted** while tenant exists; withdrawn/superseded via status. |
| Sessions, auth tokens, idempotency keys | Expired rows purged by scheduled job. |
| Audit logs | Retained per plan (UI access) but stored for at least the legal/contractual retention period; old partitions detached and archived to object storage. |

Why not a global `deleted_at` on every table: soft-delete everywhere silently breaks unique constraints and every query must remember to filter it. We soft-delete only domain entities that have a real "archived" meaning.

---

## 7. Scale & maintenance notes
- Expected size is small (see [05 §2](05-system-design.md#2-capacity-estimation-back-of-the-envelope--assumptions-not-measurements)); **no sharding** in the foreseeable plan. Partition only `audit_logs` (monthly) from day one because it's append-heavy and retention-managed; consider partitioning `published_results` by hash of tenant only if it exceeds ~100M rows.
- Bulk writes: imports and notification fan-out use `COPY`/multi-row `INSERT ... ON CONFLICT`.
- `statement_timeout` (e.g. 5 s for API role, longer for worker role), `idle_in_transaction_session_timeout`.
- Autovacuum tuned for `mark_entries` (heavy updates during entry windows).
- Backups: managed PITR (production); nightly logical dump to object storage in a different provider/region for disaster recovery; **monthly restore drill** (a backup never restored is not a backup).
