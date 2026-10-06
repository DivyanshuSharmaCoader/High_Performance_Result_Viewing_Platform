# Activity / Flow Diagrams

> Prose versions: [03 Core workflows](../03-core-workflows.md), [13 Result ingestion](../13-result-ingestion.md).

## 1. End-to-end result lifecycle (swimlanes)

```mermaid
flowchart TB
    subgraph ADMIN["Institution Admin"]
        a1["Configure exam, papers, grading"]
        a2["Assign faculty, open marks entry"]
        a5["Review completeness matrix"]
        a6["Process results"]
        a7{"Preview OK?"}
        a8["Approve"]
        a9["Publish now or schedule"]
    end
    subgraph FACULTY["Faculty"]
        f1["Enter marks in grid or import file"]
        f2{"Validation errors?"}
        f3["Fix and re-upload"]
        f4["Submit paper"]
    end
    subgraph SYSTEM["ScoreCode system"]
        s1["Validate rows into staging"]
        s2["Compute results with pinned grading version"]
        s3["Pre-render PDFs, prepare verification codes"]
        s4["Create immutable snapshots"]
        s5["Go live at publish time, notify students"]
    end
    subgraph STUDENT["Student"]
        t1["Open notification link"]
        t2["View result"]
        t3["Download marksheet"]
    end

    a1 --> a2 --> f1 --> s1 --> f2
    f2 -- yes --> f3 --> s1
    f2 -- no --> f4 --> a5 --> a6 --> s2 --> a7
    a7 -- "no, fix marks" --> f1
    a7 -- yes --> a8 --> s3 --> a9 --> s4 --> s5 --> t1 --> t2 --> t3
```

## 2. Marks import pipeline

```mermaid
flowchart TD
    start(["Upload file"]) --> chk{"Size, type, magic bytes OK?"}
    chk -- no --> rej["Reject with message"] --> stop1(["End"])
    chk -- yes --> store["Store raw file, compute SHA-256"]
    store --> dup{"Same hash already committed for this exam?"}
    dup -- yes --> warn["Warn: already imported, continue?"]
    warn --> parse
    dup -- no --> parse["Parse: encoding, delimiter, header row"]
    parse --> perr{"Parse error?"}
    perr -- yes --> failed["Job failed with readable reason"] --> stop2(["End"])
    perr -- no --> map["Auto-map columns using presets"]
    map --> conf{"Admin confirms mapping?"}
    conf -- "edit mapping" --> map
    conf -- yes --> val["Validate every row: identity, ranges, duplicates, totals, permissions"]
    val --> rep["Show report: valid / warnings / errors"]
    rep --> dec{"Errors present?"}
    dec -- "fix file" --> start
    dec -- "commit valid only" --> commit
    dec -- "no errors" --> commit["Commit in one transaction: upsert changed marks, audit"]
    commit --> stale["Mark existing result runs stale"]
    stale --> done(["Marks ready for processing"])
```

## 3. Institution onboarding

```mermaid
flowchart TD
    s(["Visit scorecode.in"]) --> form["Fill sign-up: name, email, institution, slug"]
    form --> slug{"Slug valid and free?"}
    slug -- no --> form
    slug -- yes --> mail["Send verification email"]
    mail --> clicked{"Verified within 30 min?"}
    clicked -- no --> expire(["Pending sign-up expires"])
    clicked -- yes --> prov["Provision tenant: Free plan, owner, branding, grading templates"]
    prov --> setup["Setup checklist on slug.scorecode.in/admin/setup"]
    setup --> prof["Institution profile + logo"]
    prof --> struct["Academic structure"]
    struct --> studs["Import students"]
    studs --> limit{"Within plan student limit?"}
    limit -- no --> up["Show limit and upgrade path"] --> studs
    limit -- yes --> act["Generate activation codes / invites"]
    act --> exam["Create first exam"]
    exam --> ready(["Activated tenant"])
```

## 4. Student first login (activation)

```mermaid
flowchart TD
    a(["Student opens portal"]) --> b{"Has password?"}
    b -- yes --> login["Login with enrollment no. + password"]
    b -- no --> act["Choose Activate account"]
    act --> code["Enter enrollment no. + activation code"]
    code --> ok{"Code valid, unused, unexpired?"}
    ok -- no --> lim{"Attempts exceeded?"}
    lim -- yes --> wait["Locked for 1 hour, contact institution"]
    lim -- no --> code
    ok -- yes --> setpw["Set password (length + breached check)"]
    setpw --> sess["Session created, 30-day sliding"]
    login --> sess
    sess --> dash(["Dashboard"])
```

## 5. Publication-day request handling under load

```mermaid
flowchart TD
    r(["Incoming request"]) --> cdn{"Static asset?"}
    cdn -- yes --> edge["Served by CDN"]
    cdn -- no --> rl{"Rate limit budget available?"}
    rl -- no --> r429["429 + Retry-After, UI retries with jitter"]
    rl -- yes --> kind{"Endpoint class"}
    kind -- login --> sem{"Hash slot free within 2 s?"}
    sem -- no --> r429
    sem -- yes --> hash["Argon2id verify"] --> okl["Create session"]
    kind -- "student read" --> cache{"Cache hit?"}
    cache -- yes --> resp["Return snapshot"]
    cache -- no --> db["Indexed lookup in published_results"] --> resp
    kind -- "marksheet" --> sign["Authorize + sign URL"] --> obj["Client fetches PDF from object storage"]
    kind -- "admin analytics / export" --> defer["Queue job, return 202"]
```
