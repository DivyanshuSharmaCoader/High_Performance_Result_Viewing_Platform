# Result day on the production VPS — 2026-10-14

P18.11. Two full-size attempts stalled the server before any load was applied; after the fixes they led
to (v0.1.3, v0.1.4), a step-wise run at **200 concurrent students completed with no errors**. Nothing
above 200 was tested on the VPS. The same test on a CI runner of the same size is in
[2026-10-14-result-day-ci-2vcpu.md](2026-10-14-result-day-ci-2vcpu.md).

## Set-up
`benchmarks/vps/run-on-vps.sh`: perf.yml's journey on the VPS itself, as a second Compose project
(`scorecodeperf`) beside production. It has its own containers, network and volumes, loopback ports only,
and the same synthetic data (one institution, 8,000 students, 6 papers, published through the real
services). The VPS: Hostinger KVM 2, 2 vCPU (AMD EPYC 9354P), 7.9 GB RAM, Ubuntu 24.04.5, production
`v0.1.2` then `v0.1.3` running beside it (11 containers, no users: DNS was not yet switched).

## Attempt 1 (11:13–11:54 UTC, commit 9a50881)
- Build, start, data load and publication: fine.
- **Marksheet rendering** (8,000 PDFs, the test stack's worker with 2 PDF processes): at 3,335 rendered,
  11:30, load average 3.75 and 4.8 GB available.
- About **11:32 the server stopped answering**: SSH timed out; HTTPS accepted TCP connections but never
  answered. Twenty minutes later SSH got through once and the test containers were killed (11:54).
  The owner rebooted the VPS afterwards.
- No swap; no memory limits on any container. The CI run of the same test showed the worker holding
  2.3 GB at rest after rendering. Two such workers, a build and production on 8 GB without swap: the
  likely cause was **memory exhaustion**.

## Changes after attempt 1 (released as v0.1.3, deployed 16:29)
- PDF processes are replaced every 200 marksheets (`documents/pool.py`).
- Memory limits on every production container (`compose.prod.yml`); the test stack got its own.
- A 2 GB swapfile in the server baseline (`bootstrap.sh`), swappiness 10.
- A watchdog in the test script: it stops the test stack if available memory drops under 700 MB.

## Attempt 2 (16:3x–16:54 UTC, commit 75b59ea)
- Again fine until **marksheet rendering**; again the server stopped answering, 16:45–16:54 (SSH timed
  out; HTTPS 000 from outside).
- This time **memory was not the cause**: afterwards swap was at 0 MB used, 6.7 GB available, the
  watchdog never fired, and `dmesg` had no OOM kill.
- **CPU steal:** since boot (2 h 36 min), `/proc/stat` counted 90,206 ticks of steal against about
  442,000 busy ticks, roughly **20% of the VM's busy CPU time withheld by the host**. Steal was not
  sampled over time, so how high it went during the stall is not known.
- The likely cause: sustained full use of both vCPUs (the test worker's 2 PDF processes) makes the host
  throttle the VM, and then nothing on it, sshd and Caddy included, gets CPU.

## Changes after attempt 2 (not yet released)
- The production worker is capped at **one CPU** (`cpus: 1.0`) with half the default CPU weight
  (`cpu_shares: 512`), so the API, the edge and SSH always keep a core. Production already runs one PDF
  process (`PDF_PROCESSES=1`). Expect about 45 minutes for 8,000 marksheets instead of the 24 measured
  with two processes on CI; scheduled releases render ahead of time (admin guide).
- The test stack's worker gets the same cap; its poller now waits for an explicit "finished" from the
  server and never removes anything when the server can't be reached.

## Attempt 3: step-wise, after v0.1.4 (17:15–17:52 UTC, commit 118febe)
2,000 students (6 papers, published), the test worker capped like production's (1 CPU, half weight),
**200 virtual users**: 60 s ramp, 2 min hold, each journey with 2–10 s think time. k6 ran on the same VPS
(it competes for the same 2 vCPUs, so these figures are pessimistic). Production `v0.1.4` ran beside it.

| | Pre-authenticated | Sign-in first (Argon2) |
|---|---|---|
| Requests | 25,088 · **132.3/s** | 26,202 · **138.0/s** |
| Failed | **0.00%** | **0.00%** (200 of 200 sign-ins) |
| Latest result p50 / p95 / p99 | 16.7 / 313 / 936 ms | 9.1 / 237 / 720 ms |
| Class statistics p50 / p95 / p99 | 14.5 / 265 / 816 ms | 8.1 / 208 / 663 ms |
| `/me` p50 / p95 / p99 | 33.0 / 654 / 1,483 ms | 17.9 / 472 / 1,333 ms |
| Marksheet link p50 / p95 / p99 | 37.4 / 476 / 1,292 ms | 21.3 / 356 / 1,134 ms |
| Marksheet PDF p95 | 17 ms | 13 ms |
| Sign-in p50 / p95 | — | 58.9 / 368 ms |

Server-side (the API's own log, pre-authenticated): latest p95 246 ms, statistics p95 217 ms, `/me` p95
589 ms.

**Resources** (docker stats every 5 s; k6 not included): all containers together peaked at 1.7–1.9 GB of
memory; CPU averaged 112–133% of the 200% available and peaked at 230–267%. The test API used most of it
(average 66–76%, peak 173%). **Production's worker held 108 MiB after rendering**, against 2.3 GB before
PDF processes were recycled.

**Marksheets:** 2,000 rendered in 961 s with the worker capped at one CPU, about 2.1 a second (8,000 would
take about 64 minutes). No duplicates.

**Production during the run:** 105 of 105 probes from outside (`/api/v1/plans`, every 15 s, verified
TLS) answered 200; the slowest took 0.84 s. SSH stayed reachable.

**Not measured:** host-level memory, swap and CPU steal during attempt 3 (the sampler's awk expression
was wrong and wrote nothing; fixed afterwards). Concurrency above 200.

## What this means
- **Tested on the VPS:** 200 students using the portal at once (about 135 requests a second) with no
  errors and p95 under 0.7 s for every page, while production stayed responsive. Rendering capped at one
  CPU no longer stalls the server.
- **Not tested:** more than 200 at once. CPU was already at about two-thirds of the machine at 200, so
  the 1,000-student result day the CI runner handled (with 3–6% errors) is not shown to work here.
- **Known limit:** on this plan, two cores at 100% for many minutes stalls the whole server. One stack's
  rendering capped at one core is the next thing to verify, then the k6 journey, ideally with production
  alone (no second stack) and k6 on another machine.
