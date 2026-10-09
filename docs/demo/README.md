# Demo script (P17.1, P17.2, P17.5)

A 15-minute live demonstration of ScoreCode with three demo institutions. Every step below is also an
automated test: `e2e/demo.spec.ts`, run by `.github/workflows/demo.yml` against a fresh stack. If a step
breaks, CI says so before you're on stage.

**Thapar is a demo tenant.** Its name is used with nothing else (decision D25): a generated monogram, not
the institute's logo, and 100% synthetic students and marks. Present it as "an institution like Thapar",
never as Thapar's real data.

## Before you start (10 minutes, the day before if possible)
```bash
make stack                                                    # or the demo VM (docs/runbooks/deploy-and-rollback.md)
docker compose --profile app exec -T api scorecode seed --with-history
docker compose --profile app exec -T api scorecode jobs stats  # wait until pdf/notifications show nothing queued
```

| Who | Address | Sign in |
|---|---|---|
| Thapar exam office (owner) | http://thapar.localhost:8080 | `registrar@thapar.example.com` / `scorecode-demo-2026` |
| Thapar student (COE-2A) | same | `102401001` / `scorecode-demo-2026` |
| Demo Public School (Free plan) | http://demoschool.localhost:8080 | `principal@demoschool.example.com` / same password |
| Demo Coaching Academy (Growth plan) | http://democoaching.localhost:8080 | `director@democoaching.example.com`; student `DCA251001` |
| Platform console | http://admin.localhost:8080 | `ops@scorecode.example.com`, same password, TOTP secret `SCORECODEDEMOTOTPSECRETKEYAAAAAA` (any authenticator app) |
| Verification | http://verify.localhost:8080 | anyone, no account |

Open these tabs in this order: Thapar admin, a phone-sized window for the student (devtools, 390 × 844),
the platform console, and Demo School. Keep the two files from [files/](files/) at hand.

## The script

**1. One product, many institutions (1 min).**
- Show the three institutions' sign-in pages side by side: each has its own name and colours from one
  build. Each address is an institution (host-based tenancy, docs/06).
- *Say:* "Nothing about Thapar is in the code. It's a customer like any other." The unknown-institution
  page is at any other address.

**2. The exam office (2 min).** Thapar → Exams.
- Three published end-semester exams across two academic years.
- **End semester examination, even 2026**: approved, ready to publish.
- **Mid-semester test, even 2026**: marks entry open, about 60% entered.
- Open the mid-semester test's mark sheet: the grid, autosave, the attendance codes (AB, EX, MP, WH).

**3. A spreadsheet with mistakes (3 min).** Imports → Marks → the mid-semester test → paper *UCS301 — Data
Structures*.
1. Upload `files/thapar-midsem-UCS301-with-errors.csv`. The check finds every mistake and **nothing is
   saved**:
   - Internal 45 is out of 40.
   - "fifty" isn't a number.
   - A duplicated row.
   - An enrollment number that isn't in the exam.
   - `AB` is accepted: it marks the student absent.
2. **Upload fixed file** with `files/thapar-midsem-UCS301-fixed.csv`. Then *Saves marks for 120 students*,
   and Import.
3. *Say:* every mark is checked against the paper's maximums before anything is written, and the import
   is one transaction.

**4. Publish, live (2 min).** End semester examination, even 2026 → Results.
1. *Approved and ready*, then **Publish now** to 120 students. It's live in about a second: the results
   computed at approval are frozen as immutable per-student snapshots, so reads never recompute anything.
2. In the student window (`102401001`):
   - The new result, with its **SGPA**.
   - **Earlier results** across 2024-25 and 2025-26.
   - The notification bell.
3. *Alternative:* **Schedule** two minutes ahead instead, and watch it go live by itself (the worker's
   `publishing.go_live` job).

**5. Verify a marksheet (2 min).**
1. The admin sees *marksheets are ready to download* within a minute: 120 PDFs, rendered in a process
   pool.
2. The student downloads the PDF. Scan its QR code with a phone, or open the verify address shown under
   the PDF.
3. The verify page says **Valid**, with the masked name, the exam and the PDF's SHA-256 matching the
   file.
4. *Optional:* withdraw the publication (owner, re-authentication required), and the same code now says
   **Withdrawn**, immediately.

**6. Isolation attempt (1 min).**
- Signed in at Thapar, open Demo School's address: it asks you to sign in.
- Copy Thapar's session cookie to a request for Demo School's API (devtools, or `curl -H "Cookie:
  sc_session=…" -H "Host: demoschool.localhost:8080" http://127.0.0.1:8080/api/v1/me`): **401**.
- *Say:* isolation is enforced four times over:
  1. Host resolution.
  2. A session bound to its institution.
  3. ORM criteria.
  4. PostgreSQL row-level security that fails closed.

  The isolation test suite proves every route (docs/15).

**7. Plans and limits (2 min).**
- Demo School is on **Free**: Plan shows its limits (150 students, 6 publications a year) and the locked
  features.
- Demo Coaching is on **Growth**, with a marks-and-ranks scheme. Its student `DCA251001` sees a **Rank**
  in the result. *Say:* "Same code, plans decide features. A new school starts a 30-day Pro trial once,
  and only once."

**8. The platform console (1 min).**
- Overview: institutions, students, result day.
- Institutions: the three, each with its plan.
- *Say:* ScoreCode staff see institutions, plans and health, not student marks. Suspension is one
  audited click that ends every session of that institution.

**9. The numbers (1 min, a slide).** All measured. Sources are in benchmarks/results/:
- **Result day, 1,000 students** on one 4-vCPU machine (load generator included):
  - before optimisation: 322–327 req/s, 3.3–3.6% errors, p95 4.4 s;
  - after (read cache, lazy transactions, idle-only pings, route order): **573–593 req/s, 0 errors,
    p95 0.24–0.28 s**;
  - **SQL statements per request: 6.86 → 1.65**.
- **Database restarted under load:** one 10-second window of retryable 503s, no 500s, recovered by
  itself. **Worker killed mid-render:** every marksheet exactly once.
- **Backup → database destroyed → restore:** fingerprints identical, RTO measured in CI
  (docs/runbooks/drills/).
- **Alert pipeline:** the API stopped → page email in 101 s.

## If something goes wrong on stage
- **Publish button missing:** the exam isn't approved. Use step 4's alternative on Demo School's Term 2,
  which is also approved.
- **Marksheet not ready yet:** show a previous publication's marksheet (the student's earlier results);
  they rendered after seeding.
- **Network down:** everything runs on `localhost`. Only the QR scan from a phone needs the laptop's
  network.
- **Reset everything:** `make down`, delete the volumes, then *Before you start* again (about 5 min).
