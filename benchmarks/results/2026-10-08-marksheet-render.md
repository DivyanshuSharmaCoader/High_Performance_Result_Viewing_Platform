# Marksheet PDF render time (P11.2) — 2026-10-08

**What this measures:** layout cost only. `backend/scripts/measure_marksheets.py` renders N marksheets from
synthetic six-paper snapshots (seed 2026) one after another on one thread, the way one `pdf` worker job
does. Storage and database time are not included. Each PDF is 20.7 KiB on average.

## Environment and results

| Where | Machine | Power | Per PDF p50 | p95 | Max | One thread | First render (fonts load) |
|---|---|---|---|---|---|---|---|
| Docker `test` image (Debian bookworm, Python 3.12.15, WeasyPrint 70.0, aarch64) | Apple M2 laptop, Docker Desktop VM | **battery, Low Power Mode** | 172 ms | 247 ms | 286 ms | 5.4 PDFs/s | 660 ms |
| GitHub-hosted runner (ubuntu-24.04, Python 3.12.3, x86_64; Pango from apt) | CI run 37714377613 (commit b64ff96), "Marksheet render time" step, 100 PDFs | n/a | 202 ms | 292 ms | 304 ms | 4.7 PDFs/s | 791 ms |

The laptop ran on battery with Low Power Mode, which cost this laptop 32–44% of its k6 scenario B
throughput (2026-10-08-k6-scenarios-A-B.md). It was 200 PDFs × 6 papers, after one warm-up render. The
CI runner, a common baseline that isn't on battery, came out slightly slower still. So both agree on
about **200 ms per PDF per thread**.

## What it means
- **One thread:** about 5 marksheets per second, so **8,000 students take about 25–28 minutes** on one
  worker process. WeasyPrint's layout is CPU-bound Python, so threads in the same process won't add
  much (the GIL); more `pdf` worker processes will.
- **Scheduled releases** render ahead of go-live, so result day itself does no PDF work.
- **"Publish now"** for a large cohort makes results visible at once. PDFs follow over minutes: students
  see "being prepared" on their marksheet card, and administrators see live progress.

## Next action (Phase 14)
- Render in a process pool (or run several `pdf` worker processes).
- Re-measure on AC power and on a server-class machine.
- Measure the end-to-end time for 8,000 students (render, storage and database).
