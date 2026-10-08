# API down

**Alerts:** `ScoreCodeAPIDown` (page: no API process answers), `ScoreCodeAPIInstanceDown` (warn: one
replica).
**Users see:** the SPAs load (Caddy serves them) but every action fails. Caddy retries another API address
for 3 s before answering 502/503, and the apps retry with backoff.

## Check
1. `dc ps api` shows whether the containers are up, restarting or unhealthy.
2. `dc logs --tail 200 api` usually names the problem:
   - **`Unsafe production configuration: …`** means a setting is wrong, typically after an edit to
     `env/app.env`. Fix the setting and run `dc up -d api`.
   - **`could not connect to server` or `database … does not exist`** means the database. Go to
     [database-outage.md](database-outage.md).
   - **`MemoryError` or the container being OOM-killed** (`docker inspect … State.OOMKilled`): the VM is
     too small for `API_WORKERS`. Lower it in `env/deploy.env`, or resize the VM.
   - **A traceback at import** means a bad release. Roll back
     ([deploy-and-rollback.md](deploy-and-rollback.md#roll-back)).
3. `/readyz` from inside the network (`dc exec api python -c "import urllib.request;
   print(urllib.request.urlopen('http://localhost:8000/readyz').read())"`). It reports `database: up/down`
   and `cache: redis/local`.

## Fix
- **Restart:** `dc restart api`. The healthcheck has to pass before Caddy sends traffic.
- **One replica down while others serve:** usually no user impact. Restart it and keep the logs for the
  review.
- **Still down after a restart and a rollback:** declare an incident, post a status update
  ([incident-template.md](incident-template.md)), and escalate.

## Afterwards
Note in the review what the logs said, the time to detect (the alert fires about 2–3 min after the API
stops: 1 min `for:`, scrape and evaluation intervals; measured in `ops.yml`) and the time to recover.
