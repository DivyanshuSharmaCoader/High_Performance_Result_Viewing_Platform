# Context, Container and Component Diagrams

> Explained in [05 System design](../05-system-design.md) and [08 Backend architecture](../08-backend-architecture.md).

## 1. System context (C4 level 1)

```mermaid
flowchart TB
    student["👤 Student<br/>views results, downloads marksheets"]
    staff["👤 Institution staff<br/>owner, admin, faculty"]
    padmin["👤 Platform admin<br/>ScoreCode operator"]
    verifier["👤 Verifier<br/>employer / institution"]

    sc["🟦 ScoreCode<br/>multi-tenant exam and result SaaS"]

    email["Email provider<br/>SES / Postmark"]
    pay["Payment gateway<br/>Razorpay - V1"]
    dns["DNS / CDN<br/>Cloudflare"]
    erp["Institution ERP<br/>optional integration - V1"]

    student -->|HTTPS| sc
    staff -->|HTTPS| sc
    padmin -->|HTTPS + 2FA| sc
    verifier -->|scans QR, HTTPS| sc
    sc -->|sends notifications| email
    sc -->|subscription payments| pay
    dns -->|routes tenant hosts| sc
    erp <-->|REST API / webhooks| sc
```

## 2. Containers (C4 level 2)

```mermaid
flowchart TB
    subgraph clients["Clients"]
        tenantApp["Tenant SPA<br/>React + TS<br/>student, faculty, admin"]
        platformApp["Platform console SPA<br/>React + TS"]
        site["Marketing + sign-up site<br/>static"]
        verifyPage["Verify page<br/>server-rendered HTML"]
    end

    cdn["CDN / edge<br/>static assets, TLS, WAF"]
    proxy["Reverse proxy<br/>Caddy: TLS, on-demand certs, routing"]

    subgraph app["ScoreCode application - one image"]
        api["API process<br/>FastAPI / Uvicorn<br/>stateless"]
        worker["Worker process<br/>job consumer<br/>imports, processing, PDF, notifications"]
    end

    pg[("PostgreSQL<br/>business data, sessions,<br/>job queue, audit log")]
    redis[("Redis<br/>cache + rate limits<br/>no source of truth")]
    s3[("Object storage<br/>uploads, PDFs, logos, exports")]
    mail["Email provider"]
    obs["Observability<br/>logs, metrics, Sentry"]

    tenantApp --> cdn
    platformApp --> cdn
    site --> cdn
    cdn --> proxy
    verifyPage --> proxy
    proxy --> api
    api --> pg
    api --> redis
    api -->|signed URLs| s3
    worker --> pg
    worker --> redis
    worker --> s3
    worker --> mail
    api -.-> obs
    worker -.-> obs
```

## 3. Backend component diagram (modules)

Arrows = "depends on (calls public API of)". Modules only use each other's `api.py` interfaces; enforced by import-linter.

```mermaid
flowchart LR
    subgraph web["HTTP layer"]
        routers["Routers + middleware<br/>request id, tenant resolution,<br/>rate limit, session, CSRF"]
    end

    subgraph modules["Domain modules"]
        platform["platform"]
        tenancy["tenancy"]
        identity["identity"]
        entitlements["entitlements"]
        branding["branding"]
        academics["academics"]
        directory["directory"]
        examinations["examinations"]
        grading["grading<br/>pure, no I/O"]
        marks["marks"]
        ingestion["ingestion"]
        results["results"]
        publishing["publishing"]
        documents["documents"]
        verification["verification"]
        notifications["notifications"]
        analytics["analytics"]
    end

    subgraph kernel["Shared kernel"]
        audit["audit"]
        files["files"]
        core["core<br/>db/UoW, tenant ctx, cache,<br/>jobs, config, errors, logging"]
    end

    routers --> platform
    routers --> identity
    routers --> publishing
    routers --> ingestion
    routers --> examinations

    platform --> tenancy
    platform --> entitlements
    identity --> tenancy
    entitlements --> tenancy
    branding --> entitlements
    academics --> entitlements
    directory --> identity
    directory --> academics
    directory --> entitlements
    examinations --> academics
    examinations --> directory
    examinations --> grading
    marks --> examinations
    ingestion --> marks
    ingestion --> directory
    ingestion --> files
    results --> marks
    results --> grading
    publishing --> results
    publishing --> verification
    publishing --> documents
    publishing --> notifications
    documents --> branding
    documents --> files
    notifications --> identity
    analytics --> results

    modules -.-> audit
    modules -.-> core
```

## 4. Request pipeline components

```mermaid
flowchart LR
    req["HTTP request"] --> rid["RequestID"]
    rid --> tr["TenantResolver<br/>Host to TenantContext"]
    tr --> sh["SecurityHeaders"]
    sh --> rl["RateLimiter<br/>Redis or local fallback"]
    rl --> auth["SessionAuthenticator<br/>tenant-bound"]
    auth --> csrf["CSRFGuard"]
    csrf --> perm["require permission<br/>+ require feature"]
    perm --> uow["UnitOfWork<br/>BEGIN + set app.tenant_id"]
    uow --> svc["Application service"]
    svc --> repo["TenantScopedRepository"]
    repo --> db[("PostgreSQL + RLS")]
    svc --> aud["AuditLog.record"]
    aud --> db
```
