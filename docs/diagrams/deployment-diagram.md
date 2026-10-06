# Deployment Diagrams

> Explained in [14 Deployment & operations](../14-deployment-and-operations.md). Costs in [16 Cost model](../16-cost-model.md).

## 1. Development (docker compose on a laptop)

```mermaid
flowchart TB
    browser["Browser<br/>thapar.localhost:8080<br/>admin.localhost:8080"]
    subgraph laptop["Developer machine - docker compose"]
        caddy["proxy: Caddy :8080"]
        vite["web: Vite dev servers<br/>tenant + platform"]
        api["api: FastAPI --reload"]
        worker["worker: job consumer"]
        pg[("postgres:16")]
        redis[("redis:7 - optional profile")]
        minio[("minio: S3 API")]
        mailpit["mailpit: catches email"]
    end
    browser --> caddy
    caddy -->|"/"| vite
    caddy -->|"/api"| api
    api --> pg
    api --> redis
    api --> minio
    worker --> pg
    worker --> minio
    worker --> mailpit
```

## 2. Demo (single VM)

```mermaid
flowchart TB
    users["Users<br/>thapar.demo-domain<br/>demoschool.demo-domain"]
    cf["Cloudflare<br/>DNS wildcard, CDN, TLS edge"]
    subgraph vm["VM - Indian region, 2 vCPU / 4 GB - docker compose"]
        caddy["Caddy<br/>wildcard cert via DNS-01"]
        static["Static SPA bundles"]
        api1["api x2 processes"]
        wk["worker x1"]
        pg[("PostgreSQL")]
        rd[("Redis")]
        cron["backup cron<br/>pg_dump nightly"]
    end
    r2[("Object storage<br/>R2 / S3<br/>PDFs, uploads, backups")]
    ses["Email provider"]

    users --> cf --> caddy
    caddy --> static
    caddy --> api1
    api1 --> pg
    api1 --> rd
    api1 --> r2
    wk --> pg
    wk --> r2
    wk --> ses
    cron --> r2
```

## 3. Small production

```mermaid
flowchart TB
    users["Students, staff, verifiers"]
    cf["Cloudflare<br/>DNS, CDN, WAF, DDoS"]
    pages["Static hosting<br/>tenant, platform, site SPAs"]

    subgraph region["Cloud region - India"]
        lb["Load balancer / Caddy pair<br/>TLS incl. custom domains"]
        subgraph za["Zone A"]
            app1["App node 1<br/>api container"]
            wk1["Worker node<br/>imports, processing, pdf, notify"]
        end
        subgraph zb["Zone B"]
            app2["App node 2<br/>api container"]
        end
        subgraph data["Managed data services"]
            pgp[("PostgreSQL primary")]
            pgs[("PostgreSQL standby<br/>auto failover, PITR")]
            redis[("Redis - small")]
        end
    end
    s3[("Object storage<br/>private buckets, versioning")]
    bk[("Off-site backup bucket<br/>second provider")]
    mail["Email provider"]
    mon["Monitoring<br/>Grafana, Sentry, uptime checks"]

    users --> cf
    cf --> pages
    cf --> lb
    lb --> app1
    lb --> app2
    app1 --> pgp
    app2 --> pgp
    wk1 --> pgp
    pgp -. replication .-> pgs
    app1 --> redis
    app2 --> redis
    app1 --> s3
    app2 --> s3
    wk1 --> s3
    wk1 --> mail
    pgp -. nightly dump .-> bk
    app1 -.-> mon
    app2 -.-> mon
    wk1 -.-> mon
```

## 4. Growing production

```mermaid
flowchart TB
    cf["CDN + WAF + bot management"]
    lb["Cloud load balancer"]
    subgraph platformc["Container platform - autoscaling + scheduled pre-scaling"]
        apis["api service<br/>N tasks"]
        verify["verify service<br/>same image, separate scaling"]
        wq["worker: imports + processing"]
        wpdf["worker: pdf - CPU optimised"]
        wn["worker: notifications"]
    end
    bouncer["PgBouncer / RDS Proxy"]
    pgp[("PostgreSQL primary - HA")]
    rep[("Read replica<br/>analytics, exports, platform reports")]
    redis[("Managed Redis - HA")]
    s3[("Object storage + CDN for PDFs")]

    cf --> lb
    lb --> apis
    lb --> verify
    apis --> bouncer
    verify --> bouncer
    wq --> bouncer
    wpdf --> bouncer
    wn --> bouncer
    bouncer --> pgp
    pgp -. streaming replication .-> rep
    apis --> redis
    verify --> redis
    wpdf --> s3
    apis --> s3
```

## 5. Enterprise silo (same code, dedicated stack)

```mermaid
flowchart LR
    shared["Shared ScoreCode stack<br/>Free to Pro tenants"]
    silo["Dedicated stack for one Enterprise tenant<br/>same images, same migrations,<br/>separate DB + object storage"]
    ci["CI/CD - one pipeline"]
    ci -->|deploy| shared
    ci -->|deploy| silo
```
