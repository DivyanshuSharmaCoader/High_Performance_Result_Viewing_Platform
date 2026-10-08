# Stuck publication, late or failing background work

**Alerts:**
- `ScoreCodeScheduledPublicationLate` (page): a due go-live job is still waiting 2 minutes after its time.
- `ScoreCodeWorkerDown` (page).
- `ScoreCodeQueueFallingBehind` (warn): due work waiting more than 15 min.
- `ScoreCodeDeadJobs` (warn): a job failed every attempt.

**How the work flows (docs/08):**
1. Publishing *now* makes the results visible in the request itself. Students can read them
   immediately, even if every worker is down.
2. A *scheduled* publication is a `publishing.go_live` job (queue `publishing`, 5 attempts), and only a
   worker makes it live.
3. Marksheet PDFs (`documents.render`, queue `pdf`) and notifications (`notifications.*`) follow
   publication. Students see their results while PDFs are still rendering; the download appears when it's
   ready.

## Check
```bash
dc exec api scorecode jobs stats        # due / running / dead per queue, with the oldest's age
dc exec api scorecode jobs dead         # newest dead jobs: id, queue/kind, tenant, attempts, error
dc ps worker && dc logs --tail 200 worker
```
- **Nothing running and due work waiting:** the worker is down or can't claim jobs. Look for
  `worker_claim_failed` in its log, usually the database ([database-outage.md](database-outage.md)).
- **`running` stays above 0 while nothing finishes:** a stuck job. Its lease expires (2 min by default)
  and `jobs_reap()` re-queues it automatically; a killed worker loses nothing (P14.5, exactly once).
- **The `pdf` queue is long after a large publication:** this is expected. 8,000 marksheets take about
  20 min with 2 PDF processes on a 4-vCPU runner. Act only if `oldest` keeps growing, or if `running`
  is 0.

## Fix
- **Worker down:** `dc up -d worker`. A scheduled publication goes live within seconds of the worker
  starting.
  - Running the job late is safe: `go_live` makes it live only if it is still `scheduled`. A
    publication someone cancelled meanwhile stays cancelled.
- **A dead `publishing.go_live`:**
  1. Read its error in `scorecode jobs dead`.
  2. If the cause is fixed (the database is back, for example), run it again with
     `dc exec api scorecode jobs retry <job id>`.
  3. If the institution would rather publish by hand: from the exam page, cancel the scheduled
     publication and publish now.
- **Dead `documents.render` jobs:**
  - Institution staff can use the publication's "Retry failed marksheets" (`POST …/marksheets/retry`), or
    the operator can run `scorecode jobs retry`.
  - Marksheets already rendered are skipped, so a retry never duplicates files.
- **Dead notification jobs:** retry them. The dedupe key (user + publication) prevents a second notice.
- **Falling behind on `pdf`:** raise `PDF_PROCESSES` (about 100 MB each) in `env/deploy.env` and run
  `dc up -d worker`, or start a second worker on another VM. Workers share the queue safely
  (`FOR UPDATE SKIP LOCKED`).

## Tell the institution
A late scheduled publication is visible to the institution and its students. Send the "delayed
publication" message in [incident-template.md](incident-template.md) as soon as it's over 5 minutes late.
