# Result day on the production VPS: two attempts, both stopped by the server itself — 2026-10-14

P18.11. **No latency, throughput or capacity figure was measured on the VPS.** Both attempts stopped
before the load generator started. What they found is a capacity limit of a different kind, and the
changes made because of it. The same test on a CI runner of the same size is in
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

## What this means
- **Not tested on the VPS:** concurrency, latency and error rates under 1,000 students. Do not claim a
  capacity for this server from these attempts.
- **Known limit:** on this plan, two cores at 100% for many minutes stalls the whole server. One stack's
  rendering capped at one core is the next thing to verify, then the k6 journey, ideally with production
  alone (no second stack) and k6 on another machine.
