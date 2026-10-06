# Entity-Relationship Diagrams

> Data dictionary, constraints, indexes and deletion rules: [07 Database](../07-database-design.md).
> Convention reminder: every tenant-owned table carries `tenant_id` and references parents through **composite keys `(tenant_id, id)`**. For readability `tenant_id` is shown only where it matters; `created_at`/`updated_at` are omitted.

## 1. Platform, tenancy, identity and entitlements

```mermaid
erDiagram
    plans ||--o{ plan_features : defines
    features ||--o{ plan_features : "valued in"
    tenants ||--o{ tenant_subscriptions : has
    plans ||--o{ tenant_subscriptions : "subscribed as"
    tenants ||--o{ tenant_feature_overrides : has
    features ||--o{ tenant_feature_overrides : overrides
    tenants ||--o{ tenant_usage_counters : meters
    tenants ||--o{ tenant_domains : "served on"
    tenants ||--|| tenant_settings : configures
    tenants ||--|| tenant_branding : brands
    tenants ||--o{ users : employs
    users ||--o{ user_roles : granted
    users ||--o{ sessions : opens
    users ||--o{ auth_tokens : receives
    tenants ||--o{ audit_logs : records

    plans {
        uuid id PK
        text code UK
        text name
        bigint price_paise_yearly
        bool is_public
    }
    features {
        text key PK
        text kind "boolean, limit, enum_set"
        jsonb default_value
    }
    plan_features {
        uuid plan_id PK, FK
        text feature_key PK, FK
        jsonb value "null means unlimited"
    }
    tenants {
        uuid id PK
        text slug UK
        text name
        text type
        text status
        text timezone
    }
    tenant_domains {
        text domain PK
        uuid tenant_id FK
        text status
        text verification_token
        timestamptz verified_at
    }
    tenant_subscriptions {
        uuid id PK
        uuid tenant_id FK
        uuid plan_id FK
        text status "one active per tenant"
        date period_start
        date period_end
    }
    tenant_feature_overrides {
        uuid tenant_id PK, FK
        text feature_key PK, FK
        jsonb value
        timestamptz expires_at
        text reason
    }
    tenant_usage_counters {
        uuid tenant_id PK, FK
        text metric PK
        bigint value
    }
    tenant_settings {
        uuid tenant_id PK, FK
        text approval_mode
        text student_activation_mode
        text verification_disclosure
    }
    tenant_branding {
        uuid tenant_id PK, FK
        text display_name
        uuid logo_file_id FK
        text primary_color
        text secondary_color
        text font_family
        bool show_powered_by
    }
    users {
        uuid id PK
        uuid tenant_id FK
        text login_id "UK with tenant_id"
        text email
        text password_hash
        text kind "staff or student"
        text status
    }
    user_roles {
        uuid tenant_id PK
        uuid user_id PK, FK
        text role PK
        uuid department_id FK
    }
    sessions {
        text id PK "sha256 of token"
        uuid tenant_id FK
        uuid user_id FK
        timestamptz expires_at
        timestamptz revoked_at
    }
    auth_tokens {
        text token_hash PK
        uuid tenant_id FK
        uuid user_id FK
        text purpose
        timestamptz expires_at
        timestamptz consumed_at
    }
    audit_logs {
        uuid id PK
        uuid tenant_id FK
        text actor_type
        uuid actor_id
        text action
        text entity_type
        uuid entity_id
        jsonb before
        jsonb after
        timestamptz occurred_at "partition key"
    }
```

## 2. Academic structure and directory

```mermaid
erDiagram
    tenants ||--o{ academic_sessions : has
    academic_sessions ||--o{ terms : contains
    tenants ||--o{ departments : has
    departments |o--o{ programs : groups
    departments |o--o{ courses : offers
    programs ||--o{ cohorts : "split into"
    academic_sessions ||--o{ cohorts : "runs in"
    cohorts ||--o{ cohort_memberships : includes
    students ||--o{ cohort_memberships : "belongs to"
    users |o--o| students : "account of"
    users ||--o| staff_profiles : describes

    academic_sessions {
        uuid id PK
        uuid tenant_id FK
        text code "UK with tenant_id"
        date starts_on
        date ends_on
        bool is_current
    }
    terms {
        uuid id PK
        uuid tenant_id FK
        uuid session_id FK
        text code
        int sequence
    }
    departments {
        uuid id PK
        uuid tenant_id FK
        text code "UK with tenant_id"
        text name
        timestamptz archived_at
    }
    programs {
        uuid id PK
        uuid tenant_id FK
        uuid department_id FK
        text code "UK with tenant_id"
        text name
    }
    cohorts {
        uuid id PK
        uuid tenant_id FK
        uuid program_id FK
        uuid session_id FK
        text code
        text name
    }
    courses {
        uuid id PK
        uuid tenant_id FK
        uuid department_id FK
        text code "UK with tenant_id"
        text name
        numeric credits
    }
    students {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK "nullable, unique"
        text enrollment_no "UK with tenant_id"
        text full_name
        date date_of_birth
        text status
    }
    cohort_memberships {
        uuid tenant_id PK
        uuid cohort_id PK, FK
        uuid student_id PK, FK
    }
    staff_profiles {
        uuid tenant_id PK
        uuid user_id PK, FK
        text employee_code
        text designation
        uuid department_id FK
    }
    users {
        uuid id PK
        uuid tenant_id FK
    }
    tenants {
        uuid id PK
    }
```

## 3. Examinations, marks, ingestion

```mermaid
erDiagram
    terms ||--o{ examinations : schedules
    grading_schemes ||--o{ grading_scheme_versions : versions
    grading_scheme_versions |o--o{ examinations : "pinned by"
    examinations ||--o{ exam_cohorts : "sat by"
    cohorts ||--o{ exam_cohorts : sits
    examinations ||--o{ exam_papers : contains
    courses ||--o{ exam_papers : "examined in"
    exam_papers ||--o{ paper_assignments : "assigned via"
    users ||--o{ paper_assignments : assigned
    exam_papers ||--o{ paper_submissions : tracks
    exam_papers ||--o{ mark_entries : records
    students ||--o{ mark_entries : scores
    files ||--o{ import_jobs : source
    examinations |o--o{ import_jobs : targets
    import_jobs ||--o{ import_rows : stages

    examinations {
        uuid id PK
        uuid tenant_id FK
        uuid term_id FK
        text name
        text kind
        text status
        uuid grading_scheme_version_id FK
        timestamptz scheduled_publish_at
        int version
    }
    grading_schemes {
        uuid id PK
        uuid tenant_id FK
        text name
        text strategy
    }
    grading_scheme_versions {
        uuid id PK
        uuid tenant_id FK
        uuid scheme_id FK
        int version
        jsonb config "immutable once used"
    }
    exam_cohorts {
        uuid tenant_id PK
        uuid exam_id PK, FK
        uuid cohort_id PK, FK
    }
    exam_papers {
        uuid id PK
        uuid tenant_id FK
        uuid exam_id FK
        uuid course_id FK "UK with exam_id"
        jsonb components
        numeric max_total
        numeric pass_total
        numeric credits
    }
    paper_assignments {
        uuid tenant_id PK
        uuid exam_paper_id PK, FK
        uuid cohort_id PK, FK
        uuid user_id PK, FK
    }
    paper_submissions {
        uuid tenant_id PK
        uuid exam_paper_id PK, FK
        uuid cohort_id PK, FK
        text status
        uuid submitted_by FK
    }
    mark_entries {
        uuid id PK
        uuid tenant_id FK
        uuid exam_paper_id FK
        uuid student_id FK "UK with exam_paper_id"
        jsonb components
        numeric total
        text attendance
        int version
        text source
    }
    files {
        uuid id PK
        uuid tenant_id FK
        text object_key UK
        text kind
        bigint size_bytes
        text sha256
    }
    import_jobs {
        uuid id PK
        uuid tenant_id FK
        text kind
        uuid target_exam_id FK
        uuid file_id FK
        jsonb mapping
        text status
        int rows_valid
        int rows_error
    }
    import_rows {
        uuid tenant_id PK
        uuid import_job_id PK, FK
        int row_no PK
        jsonb raw
        jsonb normalized
        jsonb issues
        text status
    }
    terms {
        uuid id PK
    }
    cohorts {
        uuid id PK
    }
    courses {
        uuid id PK
    }
    students {
        uuid id PK
    }
    users {
        uuid id PK
    }
```

## 4. Results, publication, documents, verification, notifications

```mermaid
erDiagram
    examinations ||--o{ result_runs : "processed as"
    result_runs ||--o{ student_exam_results : produces
    result_runs ||--o{ student_paper_results : produces
    result_runs ||--o{ approvals : "decided by"
    examinations ||--o{ publications : "published as"
    result_runs ||--o{ publications : source
    publications |o--o| publications : supersedes
    publications ||--o{ published_results : snapshots
    publications ||--|| exam_statistics : summarises
    students ||--o{ published_results : receives
    published_results ||--o| marksheet_documents : rendered
    files ||--o| marksheet_documents : stores
    published_results ||--|| verification_records : "verified by"
    users ||--o{ notifications : receives
    notifications ||--o{ notification_deliveries : "delivered via"

    result_runs {
        uuid id PK
        uuid tenant_id FK
        uuid exam_id FK
        int revision "UK with exam_id"
        uuid grading_scheme_version_id FK
        text input_hash
        text status
    }
    student_exam_results {
        uuid id PK
        uuid tenant_id FK
        uuid result_run_id FK
        uuid student_id FK
        numeric total
        numeric percentage
        text grade
        numeric sgpa
        text outcome
        int rank
    }
    student_paper_results {
        uuid id PK
        uuid tenant_id FK
        uuid result_run_id FK
        uuid student_id FK
        uuid exam_paper_id FK
        numeric total
        text grade
        bool passed
    }
    approvals {
        uuid id PK
        uuid tenant_id FK
        uuid result_run_id FK
        text decision
        uuid decided_by FK
        text content_hash
    }
    publications {
        uuid id PK
        uuid tenant_id FK
        uuid exam_id FK
        int version "UK with exam_id"
        uuid result_run_id FK
        text status "one published per exam"
        timestamptz scheduled_at
        timestamptz published_at
        uuid supersedes_id FK
    }
    published_results {
        uuid tenant_id PK
        uuid publication_id PK, FK
        uuid student_id PK, FK
        jsonb payload "immutable"
        text payload_hash
        timestamptz published_at
    }
    exam_statistics {
        uuid tenant_id PK
        uuid publication_id PK, FK
        jsonb stats
    }
    marksheet_documents {
        uuid id PK
        uuid tenant_id FK
        uuid publication_id FK
        uuid student_id FK
        uuid file_id FK
        text sha256
        text status
    }
    verification_records {
        text code PK "128-bit random"
        uuid tenant_id FK
        uuid publication_id FK
        uuid student_id FK
        text document_sha256
        text status
    }
    notifications {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        text type
        text title
        timestamptz read_at
    }
    notification_deliveries {
        uuid id PK
        uuid tenant_id FK
        uuid notification_id FK
        text channel
        text status
        int attempts
    }
    examinations {
        uuid id PK
    }
    students {
        uuid id PK
    }
    users {
        uuid id PK
    }
    files {
        uuid id PK
    }
```
