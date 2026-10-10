# Configuration map

Where every setting comes from, who reads it, and how it is checked. Three layers:

1. **The operator's master file** on the owner's laptop: `~/.scorecode/scorecode.env` (directory 700, file
   600, outside the repository). Template: [`infra/ops/secrets.env.example`](../infra/ops/secrets.env.example).
   Read only through [`infra/ops/with-secrets.sh`](../infra/ops/with-secrets.sh), literally, never sourced.
2. **The server's settings files**, `/opt/scorecode/env/*.env` (deploy user, mode 600) and
   `/opt/scorecode/secrets/` (Alertmanager's files), written on the server by
   [`render-env.py`](../infra/ops/server/render-env.py) from the values
   [`push-env.py`](../infra/ops/push-env.py) sends over SSH.
3. **The application's settings**: one typed module, [`backend/app/core/config.py`](../backend/app/core/config.py)
   (pydantic-settings, prefix `SCORECODE_`). It is the only place the backend reads configuration; the
   exceptions are below. Meanings and defaults: [ENVIRONMENT.md](ENVIRONMENT.md).

Nothing in this repository names the real infrastructure (server address, bucket names, account or zone
ids, email addresses): they live only in layer 1 and on the server. [`leak-scan.py`](../infra/ops/leak-scan.py)
checks every blob in history against the real values.

## Checks

| Command | What it prints |
|---|---|
| `infra/ops/with-secrets.sh check` | each master-file name with ok / MISSING / PLACEHOLDER |
| `infra/ops/with-secrets.sh run -- backend/.venv/bin/python infra/ops/secrets-check.py [--connect]` | `NAME: SET`, `MISSING`, `INVALID FORMAT` or `CONNECTION FAILED`; with `--connect`, one sanitised line per service (Cloudflare, SSH, file storage, backup storage, SMTP, GHCR, Sentry). Writes one test object under `_healthcheck/` in each bucket and deletes it; sends no email and no Sentry event |
| `infra/ops/with-secrets.sh run -- python3 infra/ops/leak-scan.py` | for each value, `not found` or where it was found (paths only) |

## 1 → 2: the master file and where each value goes

`SCORECODE_DOMAIN` is the master file's name for the domain. The application calls the same value
`SCORECODE_BASE_DOMAIN` and compose calls it `BASE_DOMAIN`: `render-env.py` writes both from the one input,
so there is one source and no second name to keep in sync.

| Master file | Server file → setting | Read by | Checked by |
|---|---|---|---|
| `SCORECODE_DOMAIN` | `app.env` `SCORECODE_BASE_DOMAIN`; `deploy.env` `BASE_DOMAIN` | API and worker (hosts, links, cookies); Caddy (site names); smoke tests | `secrets-check` (format; the Cloudflare zone's name) |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` | not sent to the server | `infra/ops/cloudflare.py` (DNS, origin certificate, SSL mode) | `secrets-check --connect` (token verifies, zone readable) |
| `DEPLOY_HOST`, `DEPLOY_SSH_USER`, `DEPLOY_SSH_PORT`, `DEPLOY_SSH_KEY_FILE` | not sent | `remote.sh`, `push-env.py`, `create-admin.py` (SSH, strict host keys) | `secrets-check --connect` (key login) |
| `FILES_S3_ENDPOINT`, `_BUCKET`, `_REGION`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | `app.env` `SCORECODE_S3_*`; `backup.env` `FILES_S3_*`, `BACKUP_FILES_S3_URI` | `core/storage` (uploads, PDFs, signed URLs); the backup job (files copy) | `--connect`: write, read, delete one object |
| `BACKUP_S3_BUCKET`, `_REGION`, `_ENDPOINT` (empty: AWS, endpoint from the region), `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | `backup.env` `BACKUP_S3_URI`, `BACKUP_S3_ENDPOINT`, `AWS_*` | `infra/backup/backup.sh`, `restore.sh` | `--connect`: write, read, delete one object |
| `BACKUP_AGE_RECIPIENT` | `backup.env` | `backup.sh` (encrypts every dump to it; the private key never reaches the server) | format (`age1…`) |
| `SMTP_HOST`, `_PORT`, `_USERNAME`, `_PASSWORD`, `MAIL_FROM` | `app.env` `SCORECODE_SMTP_*`, `SCORECODE_MAIL_FROM`; `secrets/alertmanager.yml`, `secrets/alert_smtp_password` | `core/mailer` (notices, invitations, resets); Alertmanager | `--connect`: STARTTLS and login (no email sent) |
| `ALERT_EMAIL_TO`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `secrets/alertmanager.yml`, `secrets/alert_telegram_token` | Alertmanager | format |
| `PLATFORM_ADMIN_EMAIL`, `_NAME`, `_PASSWORD` | not stored on the server | `create-admin.py` → `scorecode create-platform-user` (once) | format; the password must not appear in the repository |
| `GHCR_USERNAME`, `GHCR_READ_TOKEN` | root's Docker login (`scorecode-ctl registry-login`, token on stdin) | `scorecode-deploy` (pulls release images) | `--connect`: pull granted |
| `SENTRY_DSN` | `app.env` `SCORECODE_SENTRY_DSN` | `main` (errors only, scrubbed) | format; host reachable (no event sent) |

**Generated on the server, never sent or shown:** `POSTGRES_PASSWORD` and the five role passwords,
`SCORECODE_SECRET_KEY`, `SCORECODE_ABUSE_SIGNAL_KEY`. They are created once in `env/generated.env` (root,
600) and reused on every later `render-env`, so a re-run never changes a password.

**Fixed by the server, not configurable from outside:** the registry (`/etc/scorecode/registry`), and
`TRUSTED_PROXIES` (Cloudflare's published ranges). `API_WORKERS` (default 2) and `PDF_PROCESSES` (default 1
on the 2-vCPU server) can be passed to `push-env.py` as `API_WORKERS=3`.

## Changing a value in production

1. Edit the master file (the owner).
2. `infra/ops/with-secrets.sh run -- python3 infra/ops/push-env.py` writes the server's files again.
3. Restart what reads it: `infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl restart api`
   (and `worker`; `backup` reads its file at each run; Alertmanager: `monitoring up`).
4. For `SCORECODE_SECRET_KEY` rotation see [security-incident.md](runbooks/security-incident.md)
   (`scorecode reencrypt-secrets`). Never rotate `SCORECODE_ABUSE_SIGNAL_KEY`.

## Reads outside the settings module (deliberate)

| Where | Variable | Why |
|---|---|---|
| `backend/app/cli.py` | `SCORECODE_OLD_SECRET_KEY` | only for `reencrypt-secrets`, the previous key during a rotation; not a setting of the running app |
| `backend/app/cli.py` | `SCORECODE_PLATFORM_PASSWORD_INIT` | the first console account's password, given to the CLI through its environment instead of a command line |
| `backend/app/core/metrics.py`, `cli.py` | `PROMETHEUS_MULTIPROC_DIR` | the Prometheus client's own variable for multi-process metrics |
| `infra/` scripts | `PG*`, `AWS_*`, `BACKUP_*`, `SMOKE_*` | the backup, restore and smoke tools, configured by their own files |

## 3: application settings, their readers and tests

Generated from the code by `backend/scripts/config_map.py`; `tests/unit/test_configuration_doc.py` fails
when a setting is missing here. "Tests" lists test files that set or read the setting by name; a dash means
no test names it, though its default may still be exercised.

| Variable | Default | Read by | Tests |
|---|---|---|---|
| `SCORECODE_ENV` | `development` | `main`, `seed` | conftest, test_core, test_marksheet_render, test_metrics_multiprocess |
| `SCORECODE_SERVICE_NAME` | `scorecode` | `main` | — |
| `SCORECODE_LOG_LEVEL` | `INFO` | `main`, `worker` | — |
| `SCORECODE_LOG_JSON` | `True` | `main`, `worker` | — |
| `SCORECODE_BASE_DOMAIN` | `localhost` | `core/device`, `core/tenant`, `modules/documents/service`, `modules/entitlements/trial`, `modules/identity/security_notices`, `modules/notifications/service` … | test_core, test_notifications |
| `SCORECODE_PLATFORM_SUBDOMAIN` | `admin` | `core/tenant`, `seed` | test_core |
| `SCORECODE_VERIFY_SUBDOMAIN` | `verify` | `core/tenant`, `modules/documents/service` | — |
| `SCORECODE_PUBLIC_PORT` | `8080` | `modules/documents/service`, `modules/entitlements/trial`, `modules/identity/security_notices`, `modules/identity/service`, `modules/notifications/service`, `modules/tenancy/signup` … | test_notifications |
| `SCORECODE_PUBLIC_SCHEME` | `http` | `modules/documents/service`, `modules/entitlements/trial`, `modules/identity/security_notices`, `modules/identity/service`, `modules/notifications/service`, `modules/tenancy/signup` … | test_core, test_notifications |
| `SCORECODE_DATABASE_URL_APP` | dev URL | `core/db` | test_core, test_outages |
| `SCORECODE_DATABASE_URL_PLATFORM` | dev URL | `core/db` | test_core, test_outages |
| `SCORECODE_DATABASE_URL_MIGRATOR` | dev URL | `migrations/env` | test_core |
| `SCORECODE_DB_POOL_SIZE` | `10` | `core/db` | test_connection_usage, test_outages |
| `SCORECODE_DB_MAX_OVERFLOW` | `5` | `core/db` | test_connection_usage, test_outages |
| `SCORECODE_DB_POOL_TIMEOUT_S` | `5.0` | `core/db` | test_connection_usage, test_outages |
| `SCORECODE_DB_STATEMENT_CACHE_SIZE` | `0` | `core/db` | — |
| `SCORECODE_DB_PING_AFTER_IDLE_S` | `1.0` | `core/db` | test_outages |
| `SCORECODE_REDIS_URL` | — | `core/container` | test_connection_usage, test_outages, test_read_cache, test_security_hardening |
| `SCORECODE_REDIS_TIMEOUT_S` | `0.5` | `core/container` | — |
| `SCORECODE_REDIS_CONNECT_TIMEOUT_S` | `1.0` | `core/container` | — |
| `SCORECODE_CACHE_LOCAL_TTL_S` | `30` | `core/container` | — |
| `SCORECODE_S3_ENDPOINT_URL` | `http://localhost:59000` | `core/storage` | — |
| `SCORECODE_S3_PUBLIC_ENDPOINT_URL` | — | `core/storage` | — |
| `SCORECODE_S3_REGION` | `ap-south-1` | `core/storage` | — |
| `SCORECODE_S3_BUCKET` | `scorecode-dev` | `cli`, `core/storage` | — |
| `SCORECODE_S3_ACCESS_KEY` | `scorecode` | `core/storage` | — |
| `SCORECODE_S3_SECRET_KEY` | `(secret)` | `core/storage` | test_core |
| `SCORECODE_SIGNED_URL_TTL_S` | `300` | `core/storage` | — |
| `SCORECODE_SMTP_HOST` | `localhost` | `core/mailer`, `modules/platform/service` | — |
| `SCORECODE_SMTP_PORT` | `51025` | `core/mailer`, `modules/platform/service` | — |
| `SCORECODE_SMTP_USERNAME` | — | `core/mailer` | — |
| `SCORECODE_SMTP_PASSWORD` | — | `core/mailer` | — |
| `SCORECODE_SMTP_STARTTLS` | `False` | `core/mailer` | — |
| `SCORECODE_MAIL_FROM` | dev URL | `core/mailer` | — |
| `SCORECODE_MAIL_RATE_PER_SECOND` | `10.0` | `modules/notifications/service` | — |
| `SCORECODE_TRUST_PROXY_HEADERS` | `False` | `web/middleware` | test_auth |
| `SCORECODE_SECRET_KEY` | `(secret)` | `core/container` | test_core, test_mfa |
| `SCORECODE_ABUSE_SIGNAL_KEY` | `(secret)` | `modules/entitlements/trial` | test_core |
| `SCORECODE_RATE_TRIAL_START_PER_HOUR` | `5` | `modules/tenancy/router` | — |
| `SCORECODE_COOKIE_SECURE` | `False` | `core/device`, `modules/identity/authn`, `modules/identity/router`, `scripts/measure_read_path`, `web/middleware` | test_core, test_security_hardening |
| `SCORECODE_ARGON2_TIME_COST` | `2` | `core/security`, `scripts/measure_argon2` | — |
| `SCORECODE_ARGON2_MEMORY_KIB` | `19456` | `core/security`, `scripts/measure_argon2` | — |
| `SCORECODE_ARGON2_PARALLELISM` | `1` | `core/security`, `scripts/measure_argon2` | — |
| `SCORECODE_ARGON2_MAX_CONCURRENCY` | `4` | `core/security` | — |
| `SCORECODE_STUDENT_SESSION_DAYS` | `30` | `modules/identity/sessions` | — |
| `SCORECODE_STAFF_SESSION_IDLE_HOURS` | `12` | `modules/identity/sessions` | — |
| `SCORECODE_STAFF_SESSION_ABSOLUTE_DAYS` | `7` | `modules/identity/sessions` | — |
| `SCORECODE_PLATFORM_SESSION_HOURS` | `8` | `modules/identity/router`, `modules/identity/sessions` | — |
| `SCORECODE_RATE_LOGIN_IP_PER_MINUTE` | `3000` | `core/ratelimit` | — |
| `SCORECODE_RATE_LOGIN_IP_BURST` | `1000` | `core/ratelimit` | — |
| `SCORECODE_RATE_LOGIN_FAILURES_IP_PER_MINUTE` | `60` | `core/ratelimit` | — |
| `SCORECODE_RATE_LOGIN_FAILURES_IP_BURST` | `60` | `core/ratelimit` | — |
| `SCORECODE_RATE_SIGNUP_IP_PER_HOUR` | `5` | `core/ratelimit` | — |
| `SCORECODE_RATE_ACTIVATION_IP_PER_HOUR` | `120` | `core/ratelimit` | — |
| `SCORECODE_API_SESSION_PER_MINUTE` | `300` | `core/http` | — |
| `SCORECODE_API_SESSION_BURST` | `100` | `core/http` | test_idempotency |
| `SCORECODE_LOGIN_MAX_FAILURES` | `5` | `modules/identity/service` | test_auth |
| `SCORECODE_LOGIN_LOCKOUT_MINUTES` | `15` | `modules/identity/service` | — |
| `SCORECODE_REAUTH_WINDOW_MINUTES` | `10` | `modules/identity/service` | — |
| `SCORECODE_MAX_UPLOAD_BYTES` | `10485760` | `modules/ingestion/router`, `modules/ingestion/service` | — |
| `SCORECODE_MAX_LOGO_BYTES` | `1048576` | `modules/branding/router` | — |
| `SCORECODE_MAX_IMPORT_ROWS` | `50000` | `modules/ingestion/service` | — |
| `SCORECODE_MAX_IMPORT_COLUMNS` | `200` | `modules/ingestion/service` | — |
| `SCORECODE_MAX_XLSX_UNCOMPRESSED_BYTES` | `104857600` | `modules/ingestion/service` | — |
| `SCORECODE_WORKER_QUEUES` | `imports,processing,pdf,publishing,notifications,maintenance` | `core/jobs`, `worker` | helpers |
| `SCORECODE_WORKER_CONCURRENCY` | `4` | `worker` | — |
| `SCORECODE_STUDENT_READ_CACHE` | `True` | `modules/publishing/read_cache` | test_read_cache |
| `SCORECODE_PDF_PROCESSES` | `2` | `modules/documents/service` | — |
| `SCORECODE_WORKER_POLL_INTERVAL_S` | `1.0` | `worker` | — |
| `SCORECODE_JOB_LEASE_S` | `120` | `worker` | — |
| `SCORECODE_SENTRY_DSN` | — | `main` | — |
| `SCORECODE_METRICS_ENABLED` | `True` | `main`, `worker` | — |
| `SCORECODE_EXPOSE_DOCS` | `True` | `main` | test_core |
| `SCORECODE_BREACHED_PASSWORD_CHECK` | `True` | `core/breached` | test_breached_passwords |
| `SCORECODE_TOTP_ISSUER` | `ScoreCode` | `modules/identity/mfa`, `modules/platform/bootstrap` | — |
