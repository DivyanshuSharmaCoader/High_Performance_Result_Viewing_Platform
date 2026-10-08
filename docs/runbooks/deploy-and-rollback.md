# Deploy and roll back

## Install a server (once)
1. **A VM** (Ubuntu 24.04, 2–4 vCPU, 4–8 GB, Indian region). Install Docker. Create a `deploy` user in the
   `docker` group, with SSH keys only.
2. **Cloudflare (D23):** the domain's DNS on Cloudflare.
   - DNS: `A @` and `A *` → the VM, both proxied.
   - SSL/TLS: "Full (strict)". Edge certificates: "Always Use HTTPS".
   - Create an **Origin certificate** for `*.domain` and `domain`. Save it as
     `/opt/scorecode/certs/origin.pem` and `origin-key.pem`, owned by root, mode 600.
   - Firewall: allow 443 only from Cloudflare's ranges, and 22 from your addresses.
3. **Files:** `/opt/scorecode` holds `compose.prod.yml` and `infra/` from the release (the deploy job
   copies them), plus:
   - `env/` (mode 700), filled in from `infra/ops/env/*.example` (mode 600). Every secret is new and
     random.
   - `secrets/alert_smtp_password` and `infra/monitoring/alertmanager.prod.yml`, if you run monitoring
     on the VM.
4. **GHCR:** `docker login ghcr.io` with a token that can only read packages.
5. **First deploy:** `SKIP_BACKUP=1 SMOKE_TENANT= infra/ops/deploy.sh vX.Y.Z`. Then create the first
   platform user with `dc exec api scorecode create-platform-user --email … --name …`. It prints the TOTP
   enrolment once.
6. **GitHub:**
   - Repository secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS`.
   - Variable `PRODUCTION_DOMAIN`.
   - An Environment `production` with required reviewers.

## Release
1. Merge to `main` with CI green. The release rehearsal (`release.yml`) runs on every change to the
   deploy files.
2. `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `release.yml` builds the four images, scans them (fixable critical vulnerabilities stop it) and pushes
   them to GHCR.
4. It waits for approval on the `production` environment, then deploys over SSH with
   `infra/ops/deploy.sh`:
   1. A backup with the running version.
   2. Migrations (expand-only).
   3. A restart.
   4. A smoke test on the VM.
   5. An automatic rollback on failure.
5. A second smoke test runs through Cloudflare with real certificates.

**Downtime:** on one VM, about 5–10 s while the API restarts. Caddy retries for 3 s and the apps retry
503s. Zero-downtime rolling deploys need two API hosts behind a load balancer (docs/14 N3).

## Migrations rule
- **Expand-only in a release.** Add columns, tables and indexes; make new columns nullable or give them
  defaults. The previous version must run on the new schema, because rollback depends on it.
- **Contract** (drop or rename) one release later, when no running version uses the old shape.

## Roll back
- **Automatic:** `deploy.sh` starts the previous version again if the new one doesn't become healthy or
  fails the smoke test. Check `deploy.log`.
- **By hand:** `infra/ops/deploy.sh vPREVIOUS`. Images stay in GHCR, and the schema is compatible (see
  above).
- **If a release corrupted data:** this is not a rollback, it's a restore
  ([backup-and-restore.md](backup-and-restore.md)), from the backup `deploy.sh` took just before.
