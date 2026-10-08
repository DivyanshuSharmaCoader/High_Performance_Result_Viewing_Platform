# Security incident

**Alerts:** `ScoreCodeLoginFailureSpike` (warn). Other reports may come from an institution, a student,
a researcher, or a scan.
**First:** open an incident note ([incident-template.md](incident-template.md)), keep evidence, and change
nothing you can't explain later. Audit logs are append-only and partitioned by month. Don't drop
partitions during an incident.

## Credential stuffing (many failed sign-ins)
- The defences are on already:
  - Argon2id with bounded concurrency.
  - A failure bucket of 60/min per real client address. The address comes from Caddy's `X-Real-IP`, and
    behind Cloudflare it is the visitor's address, never Cloudflare's.
  - Per-account limits and progressive lockout.
  - Breached-password checks on every new password.
- **Check:** the dashboard's "sign-ins per minute by outcome". If one address dominates, block it in
  Cloudflare (WAF rule).
- **If it's distributed** (many addresses): turn on Cloudflare's managed challenge for `/api/v1/auth/*`
  on the affected host for the duration.
- **Accounts that did get in** (an unusual `success` spike for one tenant):
  - The institution resets those passwords.
  - Each user can end their own sessions everywhere ("Sign out everywhere").
  - Platform: suspending the tenant revokes all its sessions at once.

## A secret leaked
Rotate it, then check the audit logs for use in between. Rotations, and what each one costs:

| Secret | Where | Rotate | Side effects |
|---|---|---|---|
| Database role passwords | `env/db.env`, `env/app.env`, `env/backup.env`, `env/monitoring.env` | `ALTER ROLE scorecode_app PASSWORD '…'` (as postgres), update the env files, `dc up -d` | None |
| `SCORECODE_SECRET_KEY` | `env/app.env` | Set the new value, then **`SCORECODE_OLD_SECRET_KEY=<old> dc run --rm api scorecode reencrypt-secrets`** (try `--dry-run` first), then `dc up -d api worker` | It encrypts two-step (TOTP) secrets. Without the re-encryption every two-step sign-in fails. The command re-encrypts staff and platform users and is safe to run twice |
| `SCORECODE_ABUSE_SIGNAL_KEY` | `env/app.env` | New value, `dc up -d api worker` | Earlier trial claims no longer match new sign-ups, so the one-trial-per-institution check forgets past claimants |
| Object storage keys | `env/app.env`, `env/backup.env` | Create new keys at the provider, update, restart, delete the old keys | None |
| SMTP credentials | `env/app.env` | New credentials at the provider, update, restart | None |
| Cloudflare origin certificate | `certs/` | Issue a new one in Cloudflare, replace the files, `dc restart proxy`, revoke the old one | None |
| age backup key (private) | the vault | New key pair; new public key in `env/backup.env` | Old backups stay readable with the leaked key: delete what you can, and shorten retention |
| A platform user's password or TOTP | — | Disable the user (`platform_users.status`), create a new one with `scorecode create-platform-user` | — |

Sessions survive key rotations: they are random tokens stored hashed, not signed. To end everyone's
sessions after a broad compromise, as postgres:
`UPDATE sessions SET revoked_at = now() WHERE revoked_at IS NULL` and the same for `platform_sessions`.
Everyone signs in again.

## Suspected cross-tenant exposure
This is the most serious kind of incident: isolation is the product's core promise (docs/06).
1. **Preserve:** take a backup now (`dc run --rm backup backup.sh`) and keep the logs (`dc logs > …`).
2. **Find the request:** API logs carry `request_id`, `tenant_id` and route. Audit logs record who saw or
   changed what.
3. **Contain:**
   - If the route is known, disable it: deploy a hotfix, or block the path in Cloudflare.
   - Suspend the affected tenants in the platform console if needed.
4. **Prove the fix with a test:** the isolation suite (`tests/integration/test_isolation.py`) must gain
   the case that leaked.

## Who must be told (India)
These are the obligations as understood when this was written (2026). Confirm them with counsel at the
time.
- **Affected institutions, without delay.** Each institution is the data fiduciary for its students'
  data under the DPDP Act 2023, and ScoreCode processes the data on its behalf. Institutions notify the
  Data Protection Board and affected students; give them what they need to do it.
- **CERT-In within 6 hours** of noticing a reportable cyber security incident (CERT-In Directions, April
  2022).
- Use the templates in [incident-template.md](incident-template.md). Be factual: what happened, what data,
  which institutions, what's done, what's next.
