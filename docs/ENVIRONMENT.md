# Configuration reference

All backend settings are environment variables with the prefix `SCORECODE_`, parsed by
`backend/app/core/config.py` (pydantic-settings). In `staging`/`production` the app **refuses to start**
with development secrets, insecure cookies, a non-HTTPS public scheme or development database passwords.

| Variable | Default | Purpose |
|---|---|---|
| `SCORECODE_ENV` | `development` | `development`, `test`, `staging`, `production` |
| `SCORECODE_SERVICE_NAME` | `scorecode` | Name in structured logs |
| `SCORECODE_TOTP_ISSUER` | `ScoreCode` | Name shown in authenticator apps for two-step sign-in |
| `SCORECODE_BASE_DOMAIN` | `localhost` | Tenants live at `<slug>.<base>`; console at `admin.<base>`; verification at `verify.<base>` (decision D23 is open, so nothing is hard-coded) |
| `SCORECODE_PLATFORM_SUBDOMAIN` / `SCORECODE_VERIFY_SUBDOMAIN` | `admin` / `verify` | Reserved subdomains |
| `SCORECODE_PUBLIC_SCHEME` / `SCORECODE_PUBLIC_PORT` | `http` / `8080` | Used to build absolute links in emails |
| `SCORECODE_DATABASE_URL_APP` | dev URL | Runtime role `scorecode_app` (NOBYPASSRLS) |
| `SCORECODE_DATABASE_URL_PLATFORM` | dev URL | Platform-console role `scorecode_platform` (BYPASSRLS) |
| `SCORECODE_DATABASE_URL_MIGRATOR` | dev URL | Schema owner, used only by `scorecode migrate` |
| `SCORECODE_DB_POOL_SIZE` / `_MAX_OVERFLOW` / `_POOL_TIMEOUT_S` | `10` / `5` / `5.0` | Connections per process; a request that waits longer than the timeout gets `503 overloaded` + `Retry-After` |
| `SCORECODE_DB_STATEMENT_CACHE_SIZE` | `0` | asyncpg's prepared-statement cache; 0 keeps the app compatible with PgBouncer transaction pooling |
| `SCORECODE_REDIS_URL` | unset | Optional cache and shared rate limits; the app works without it |
| `SCORECODE_REDIS_TIMEOUT_S` / `_CONNECT_TIMEOUT_S` | `0.5` / `1.0` | A circuit breaker stops repeated waits when Redis is unhealthy |
| `SCORECODE_CACHE_LOCAL_TTL_S` | `30` | In-process cache lifetime (tenant configuration and similar), in front of Redis |
| `SCORECODE_S3_ENDPOINT_URL` | `http://localhost:59000` | S3 API endpoint used by the app |
| `SCORECODE_S3_PUBLIC_ENDPOINT_URL` | unset | Endpoint browsers use for signed download URLs |
| `SCORECODE_S3_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` / `_REGION` | dev values | Object storage (private bucket) |
| `SCORECODE_SIGNED_URL_TTL_S` | `300` | Lifetime of signed download links (marksheets, logos) |
| `SCORECODE_SMTP_HOST` / `_PORT` / `_USERNAME` / `_PASSWORD` / `_STARTTLS` | Mailpit | Outgoing email (SES/Postmark SMTP in production) |
| `SCORECODE_MAIL_FROM` | `ScoreCode <no-reply@scorecode.localhost>` | Sender address (deliverability: docs/14 §R) |
| `SCORECODE_MAIL_RATE_PER_SECOND` | `10` | Emails per second per sending job; keep the total under the provider's rate |
| `SCORECODE_MAIL_DAILY_LIMIT` | `0` (none) | Emails in any 24 hours, for every process together: the email plan's daily cap (production 280, under Brevo free's 300) |
| `SCORECODE_MAIL_DAILY_RESERVE` | `60` | Part of the daily limit result notices leave for password resets, invitations and security notices |
| `SCORECODE_MAIL_NOTICE_MAX_DELAY_HOURS` | `48` | A result notice that can't be sent within this long after publishing is skipped (`daily-limit`); the portal shows the result anyway |
| `SCORECODE_SECRET_KEY` | dev value | ≥ 32 chars; derives the field-encryption key (TOTP secrets) |
| `SCORECODE_ABUSE_SIGNAL_KEY` | dev value | ≥ 32 chars, required outside development. Keys the hashes of trial identity signals (docs/12 §6). **Never rotate it**: a new key forgets every trial already taken. |
| `SCORECODE_RATE_TRIAL_START_PER_HOUR` | 5 | Trial start attempts per client IP |
| `SCORECODE_RATE_LOGIN_IP_PER_MINUTE` / `_BURST` | 3000 / 1000 | Every sign-in attempt per IP: a flood ceiling, because whole classes share an address |
| `SCORECODE_RATE_LOGIN_FAILURES_IP_PER_MINUTE` / `_BURST` | 60 / 60 | Failed sign-ins per IP (credential stuffing) |
| `SCORECODE_COOKIE_SECURE` | `false` | `true` outside development → `__Host-` prefixed, Secure cookies |
| `SCORECODE_TRUST_PROXY_HEADERS` | `false` | Take the client IP from `X-Real-IP`, which our Caddy overwrites — only behind our own proxy. `X-Forwarded-For` is never read by the API (docs/10 §7) |
| `SCORECODE_ARGON2_TIME_COST` / `_MEMORY_KIB` / `_PARALLELISM` / `_MAX_CONCURRENCY` | `2` / `19456` / `1` / `4` | Password hashing cost and per-process concurrency (measured: benchmarks/results) |
| `SCORECODE_STUDENT_SESSION_DAYS` | `30` | Sliding student session |
| `SCORECODE_STAFF_SESSION_IDLE_HOURS` / `_ABSOLUTE_DAYS` | `12` / `7` | Staff session limits |
| `SCORECODE_PLATFORM_SESSION_HOURS` | `8` | Console session |
| `SCORECODE_LOGIN_MAX_FAILURES` / `_LOCKOUT_MINUTES` | `5` / `15` | Progressive account lockout |
| `SCORECODE_REAUTH_WINDOW_MINUTES` | `10` | Password re-confirmation window for sensitive actions |
| `SCORECODE_RATE_SIGNUP_IP_PER_HOUR` | `5` | Self-serve sign-ups per IP |
| `SCORECODE_RATE_ACTIVATION_IP_PER_HOUR` | `120` | Student activation attempts per IP (burst = half); per enrollment no. stays 5/hour |
| `SCORECODE_MAX_UPLOAD_BYTES` / `_MAX_IMPORT_ROWS` / `_MAX_IMPORT_COLUMNS` / `_MAX_XLSX_UNCOMPRESSED_BYTES` | 10 MB / 50,000 / 200 / 100 MB | Hard caps for spreadsheet imports (plans can be stricter via `max_import_rows`) |
| `SCORECODE_API_SESSION_PER_MINUTE` / `_BURST` | `300` / `100` | Authenticated API calls per session |
| `SCORECODE_MAX_UPLOAD_BYTES` / `_MAX_LOGO_BYTES` | 10 MB / 1 MB | Upload size limits |
| `SCORECODE_WORKER_QUEUES` / `_CONCURRENCY` / `_POLL_INTERVAL_S` / `SCORECODE_JOB_LEASE_S` | see code | Background worker |
| `SCORECODE_PDF_PROCESSES` | `2` | Marksheet layout processes per worker (spawned; about 100 MB each). `0` lays out in a thread. Measured scaling: benchmarks/results/2026-10-08-marksheet-render.md |
| `SCORECODE_STUDENT_READ_CACHE` | `true` | Caches the student read path's immutable rows (publishing/read_cache.py). `false` turns it off, as an escape hatch and for before/after runs (`perf.yml` `compare=cache`) |
| `SCORECODE_DB_PING_AFTER_IDLE_S` | `1.0` | A pooled connection idle longer than this is pinged before use; busier ones are not (core/db.py `_ping_if_idle`) |
| `SCORECODE_OLD_SECRET_KEY` | — | Only for `scorecode reencrypt-secrets`, after `SCORECODE_SECRET_KEY` changed: the previous key, to re-encrypt two-step secrets (docs/runbooks/security-incident.md). Remove it afterwards |
| `API_WORKERS` (compose) | `2` | Uvicorn worker processes per API container; scale containers with `docker compose up --scale api=N` (Caddy balances across them) |
| `SCORECODE_SENTRY_DSN` | unset | Error reporting, errors only, scrubbed of personal data (`app/core/sentry.py`). `scorecode sentry-test` sends one synthetic error |
| `SCORECODE_RELEASE` | unset | The deployed version, attached to error reports; compose sets it from `SCORECODE_VERSION` |
| `SCORECODE_METRICS_ENABLED` | `true` | `/metrics` for Prometheus (scraped inside the server only; the edge doesn't route it) |
| `SCORECODE_LOG_LEVEL` / `SCORECODE_LOG_JSON` | `INFO` / `true` | Structured logs; secrets and personal data are redacted |
| `SCORECODE_EXPOSE_DOCS` | `true` | `/api/docs` and `/api/openapi.json`. Must be `false` outside development (refused at start-up) |
| `SCORECODE_BREACHED_PASSWORD_CHECK` | `true` | Refuse passwords found in breaches (Have I Been Pwned range API: only 5 hash characters leave the server; fails open after 2 s). Needs outbound HTTPS to `api.pwnedpasswords.com` |

Frontend apps have no runtime configuration: the tenant, its branding and features come from
`GET /api/v1/tenant/config` on the same origin. The Caddy edge reads `BASE_DOMAIN`, `FILES_ORIGIN` and
`TRUSTED_PROXIES`: the proxies allowed to tell Caddy the client address (default `private_ranges`; in
production, the CDN's published ranges, space-separated). Caddy reads `X-Forwarded-For` from the right, skips
those proxies, and overwrites `X-Real-IP` with the first address it does not trust.

## Troubleshooting the local stack

- **Image builds hang at "resolve image config" / "load metadata", and `docker pull` hangs too.** On macOS
  the Docker Desktop credential helper (`credsStore: desktop`, backed by the Keychain) can block after a
  restart, usually on a Keychain prompt. Unlock or approve it. To build without stored credentials (all base
  images are public), point one command at an empty config:
  `DOCKER_CONFIG=$(mktemp -d) DOCKER_HOST=unix://$HOME/.docker/run/docker.sock docker compose --profile app up -d --build`
  (symlink `~/.docker/cli-plugins` into that directory first so `docker compose` is found).
- **Repeated local E2E runs start failing with "Too many requests".** Rate limits live in Redis and outlast
  the run; the compose app profile relaxes them, or flush Redis with `docker compose exec redis redis-cli FLUSHDB`.
