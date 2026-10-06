# Collaboration (Communication) Diagrams

> UML communication diagrams emphasise **which objects collaborate** and the **numbered order of messages** between them (the same information as a sequence diagram, organised around structure rather than time). Mermaid has no native communication diagram, so these use flowcharts with numbered message labels on links.

## 1. Publishing an exam's results

```mermaid
flowchart LR
    admin(["👤 :InstitutionAdmin"])
    router[":PublicationRouter"]
    svc[":PublicationService"]
    ent[":Entitlements"]
    res[":ResultRepository"]
    pub[":PublicationRepository"]
    snap[":SnapshotBuilder"]
    ver[":VerificationService"]
    aud[":AuditLog"]
    jobs[":JobQueue"]
    uow[":UnitOfWork"]

    admin -- "1: POST /exams/id/publications" --> router
    router -- "2: publish(exam_id, when)" --> svc
    svc -- "3: require(scheduled_publication)<br/>4: check_limit(published_exams_per_year)" --> ent
    svc -- "5: begin(tenant ctx)" --> uow
    svc -- "6: approved_run(exam_id)" --> res
    svc -- "7: build(run) per student" --> snap
    svc -- "8: create(publication, snapshots)" --> pub
    svc -- "9: attach(codes, pending)" --> ver
    svc -- "10: record(publication.scheduled)" --> aud
    svc -- "11: enqueue(publish_scheduled, at)" --> jobs
    svc -- "12: commit()" --> uow
    router -- "13: 201 Created" --> admin
```

## 2. Validating an uploaded marks file (worker side)

```mermaid
flowchart LR
    worker[":Worker"]
    pipe[":ImportPipeline"]
    store[":FileStore"]
    parser[":XlsxParser"]
    profile[":MarksImportProfile"]
    ctx[":ValidationContext"]
    rules[":ValidationRule list"]
    rows[":ImportRowRepository"]
    job[":ImportJob"]

    worker -- "1: run(job_id)" --> pipe
    pipe -- "2: get(object_key)" --> store
    pipe -- "3: rows(stream)" --> parser
    pipe -- "4: load_context(tenant, exam)" --> profile
    profile -- "5: students, papers, cohorts" --> ctx
    pipe -- "6: check(row, ctx) for each rule" --> rules
    pipe -- "7: bulk_insert(outcomes)" --> rows
    pipe -- "8: mark_validated(counts)" --> job
```

## 3. Student reading a result (read path)

```mermaid
flowchart LR
    st(["👤 :Student"])
    mw[":TenantResolver + SessionAuthenticator"]
    q[":StudentResultsQuery"]
    cache[":Cache"]
    repo[":PublishedResultRepository"]
    db[(":PostgreSQL")]

    st -- "1: GET /me/results/latest" --> mw
    mw -- "2: principal(student_id, tenant_id)" --> q
    q -- "3: get(t:tid:pub:...)" --> cache
    q -- "4 [miss]: latest_for(student_id)" --> repo
    repo -- "5: SELECT with tenant ctx + RLS" --> db
    q -- "6 [miss]: set(immutable key)" --> cache
    q -- "7: ResultView" --> st
```

## 4. Tenant onboarding

```mermaid
flowchart LR
    owner(["👤 :Prospective owner"])
    signup[":SignupService"]
    tok[":AuthTokenService"]
    mail[":Mailer"]
    prov[":TenantProvisioner"]
    ent[":PlanService"]
    idn[":UserService"]
    brand[":BrandingService"]
    aud[":AuditLog"]

    owner -- "1: submit sign-up form" --> signup
    signup -- "2: issue(email_verification)" --> tok
    signup -- "3: send verification link" --> mail
    owner -- "4: click link" --> signup
    signup -- "5: create tenant(slug, name, type)" --> prov
    prov -- "6: start subscription(free)" --> ent
    prov -- "7: create owner user + role" --> idn
    prov -- "8: create default branding + grading templates" --> brand
    prov -- "9: record(tenant.created)" --> aud
    signup -- "10: redirect to slug.scorecode.in/admin/setup" --> owner
```
