# Sequence Diagrams

> Key interactions. Workflows in prose: [03 Core workflows](../03-core-workflows.md).

## 1. Tenant resolution and authenticated request

```mermaid
sequenceDiagram
    autonumber
    actor U as Student browser
    participant P as Caddy proxy
    participant A as API (FastAPI)
    participant C as Redis / in-process cache
    participant D as PostgreSQL

    U->>P: GET https://thapar.scorecode.in/api/v1/me/results/latest (cookie __Host-sc_session)
    P->>A: forward with original Host header
    A->>C: get tenant for host thapar.scorecode.in
    alt cache miss
        A->>D: SELECT tenant by slug
        D-->>A: tenant row (status active)
        A->>C: store host mapping (TTL 60 s)
    end
    A->>A: build TenantContext
    A->>C: get session by SHA-256(token)
    alt cache miss
        A->>D: SELECT session by id hash
        D-->>A: session (user_id, tenant_id, expires_at)
    end
    A->>A: verify session.tenant_id equals TenantContext.tenant_id
    alt mismatch or expired
        A-->>U: 401 problem+json
    else valid
        A->>D: BEGIN, set_config app.tenant_id (transaction-local)
        A->>D: SELECT published_results WHERE tenant_id and student_id ORDER BY published_at DESC LIMIT 1
        Note over D: RLS policy also filters by app.tenant_id
        D-->>A: snapshot payload
        A->>D: COMMIT
        A-->>U: 200 result JSON (Cache-Control private, no-store)
    end
```

## 2. Login with rate limiting and Argon2id

```mermaid
sequenceDiagram
    autonumber
    actor U as User browser
    participant A as API
    participant R as Rate limiter (Redis)
    participant H as Hash pool (bounded semaphore)
    participant D as PostgreSQL

    U->>A: POST /api/v1/auth/login (login_id, password, CSRF token)
    A->>R: consume token: login per IP and per account
    alt bucket empty
        A-->>U: 429 Retry-After
    else allowed
        A->>D: SELECT user by tenant_id and login_id
        A->>H: acquire slot
        alt no slot within 2 s
            A-->>U: 429 Retry-After (UI retries with jitter)
        else slot acquired
            H->>H: argon2id verify (password or dummy hash if user missing)
            H-->>A: result
            alt invalid
                A->>D: increment failed_login_count, audit login_failed
                A-->>U: 401 generic message
            else valid
                A->>D: INSERT session (id = SHA-256 of new random token), reset counters
                A->>D: audit user.login
                A-->>U: 200 + Set-Cookie __Host-sc_session (HttpOnly, Secure, SameSite Lax)
            end
        end
    end
```

## 3. Marks import: upload, validate, commit

```mermaid
sequenceDiagram
    autonumber
    actor Ad as Admin / Faculty
    participant A as API
    participant S as Object storage
    participant D as PostgreSQL (+ job queue)
    participant W as Worker

    Ad->>A: POST /imports (multipart file, exam_id, kind=marks)
    A->>A: authorize, check size and type, check entitlement limits
    A->>S: PUT tenants/tid/imports/uuid
    A->>D: BEGIN, INSERT import_jobs (uploaded, sha256), enqueue parse_and_validate, audit, COMMIT
    A-->>Ad: 202 Accepted (job id)
    W->>D: fetch job (SKIP LOCKED), set tenant context
    W->>S: GET file
    W->>W: parse (encoding, header row), auto-map columns
    W->>D: load students, cohorts, papers for exam (one query each)
    W->>W: validate rows in memory
    W->>D: COPY import_rows, update job counts, status validated
    loop every 2 s until validated
        Ad->>A: GET /imports/{id}
        A-->>Ad: status and counts
    end
    Ad->>A: GET /imports/{id}/rows?status=error
    A-->>Ad: issues table (or annotated XLSX download)
    Ad->>A: POST /imports/{id}/commit (Idempotency-Key)
    A->>D: BEGIN, enqueue commit_import, COMMIT
    W->>D: BEGIN, set tenant ctx, upsert mark_entries (changed only), mark result runs stale, audit import.committed, job committed, COMMIT
    Ad->>A: GET /imports/{id}
    A-->>Ad: committed (n new, m updated)
```

## 4. Result processing and approval

```mermaid
sequenceDiagram
    autonumber
    actor Ad as Admin
    actor Ch as Checker admin (maker-checker mode)
    participant A as API
    participant D as PostgreSQL
    participant W as Worker
    participant G as GradingEngine (pure)
    participant S as Object storage

    Ad->>A: POST /exams/{id}/process (Idempotency-Key)
    A->>D: verify all papers submitted, INSERT result_runs (revision n, running), enqueue job
    A-->>Ad: 202 (job id)
    W->>D: load marks, papers, pinned grading scheme version
    W->>G: compute(inputs, scheme)
    G-->>W: per-student results (deterministic)
    W->>D: bulk insert student_exam_results and student_paper_results, input_hash, status completed
    Ad->>A: GET /exams/{id}/preview and /anomalies
    A-->>Ad: distribution, anomalies, per-student preview
    alt single-step approval
        Ad->>A: POST /exams/{id}/approve (re-auth)
    else maker-checker
        Ch->>A: POST /exams/{id}/approve (re-auth, checker differs from processor)
    end
    A->>D: BEGIN, lock marks, INSERT approvals (content_hash), exam status approved, enqueue render_marksheets, audit, COMMIT
    W->>D: load results in chunks
    W->>W: render HTML template to PDF with QR (verification code pre-generated, status pending)
    W->>S: PUT PDFs under tenants/tid/marksheets
    W->>D: marksheet_documents rendered (sha256)
```

## 5. Publication (immediate or scheduled)

```mermaid
sequenceDiagram
    autonumber
    actor Ad as Admin
    participant A as API
    participant D as PostgreSQL
    participant W as Worker
    participant C as Cache
    participant E as Email provider

    Ad->>A: POST /exams/{id}/publications (when = now or 10:00, Idempotency-Key)
    A->>A: require approved run, entitlement check (published exams per year, scheduled_publication)
    A->>D: BEGIN, INSERT publications (version v, scheduled), INSERT published_results snapshots (one per student), INSERT exam_statistics, COMMIT
    A-->>Ad: 201 publication (scheduled)
    Note over W: at scheduled_at (job with schedule_at)
    W->>D: BEGIN, publication status published, previous version superseded, verification records active (old ones superseded), audit publication.published, enqueue fanout, COMMIT
    W->>C: warm tenant caches (stats, publication status)
    W->>D: bulk insert notifications for affected students
    loop batches of N recipients, provider rate limit
        W->>E: send email batch (link only, no marks)
        E-->>W: accepted ids
        W->>D: update notification_deliveries
    end
```

## 6. Student views result and downloads marksheet

```mermaid
sequenceDiagram
    autonumber
    actor St as Student (phone)
    participant CDN as CDN
    participant A as API
    participant D as PostgreSQL
    participant S as Object storage

    St->>CDN: GET thapar.scorecode.in (index.html + hashed assets)
    CDN-->>St: SPA bundle (cached at edge)
    St->>A: GET /api/v1/tenant/config
    A-->>St: branding tokens (ETag)
    St->>A: GET /api/v1/me/results/latest
    A->>D: one indexed lookup on published_results (tenant_id, student_id)
    D-->>A: snapshot
    A-->>St: result JSON
    St->>A: POST /api/v1/me/results/{pub}/marksheet-url
    A->>D: check the snapshot belongs to this student and publication is published
    A->>A: sign URL for tenants/tid/marksheets/key (expires in 5 min)
    A-->>St: signed URL
    St->>S: GET signed URL
    S-->>St: PDF bytes (app servers never stream the file)
```

## 7. Third-party verification

```mermaid
sequenceDiagram
    autonumber
    actor V as Verifier
    participant A as API (verify host)
    participant R as Rate limiter
    participant D as PostgreSQL

    V->>A: GET https://verify.scorecode.in/v/7KQ3-M9XD-PA2F-8RTC-WV6H-Q
    A->>R: per-IP bucket
    alt limited
        A-->>V: 429 page
    else allowed
        A->>D: SELECT verification_records by code (platform role, read-only, audited count)
        alt not found
            A-->>V: generic not found page (noindex)
        else found
            A->>D: load tenant display data and masked snapshot fields
            A-->>V: HTML: institution, exam, date, status (Valid / Superseded / Withdrawn / Revoked), masked name, document hash
            opt tenant allows challenge
                V->>A: POST DOB or consent PIN
                A-->>V: full result summary
            end
        end
    end
```

## 8. Correction and re-publication

```mermaid
sequenceDiagram
    autonumber
    actor Ad as Admin
    participant A as API
    participant D as PostgreSQL
    participant W as Worker

    Ad->>A: POST /exams/{id}/corrections (reason)
    A->>D: exam status correction_draft, unlock affected papers, audit
    Ad->>A: PUT marks for affected students (grid or import)
    Ad->>A: POST /exams/{id}/process
    W->>D: result run revision n+1
    Ad->>A: GET /publications/{v}/diff
    A-->>Ad: changed students old vs new
    Ad->>A: POST /exams/{id}/approve then /publications
    W->>D: publication v+1 published, v superseded, old verification records superseded, new ones active
    W->>D: notify only changed students (result revised)
```
