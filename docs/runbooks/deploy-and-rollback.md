# Deploy and roll back

## Install a server (once)
Everything runs from the operator's Mac through the secrets loader (`infra/ops/with-secrets.sh run -- …`);
no value is typed, printed or put on a command line. `remote.sh` steps run over SSH with host keys checked.

1. **A VM** (Ubuntu 24.04, 2–4 vCPU, 4–8 GB, Indian region), reachable as root with the operator's key.
2. **Baseline:** `remote.sh root inspect` (read-only), then `remote.sh root apply`:
   - unattended security updates, NIC/NPL time, Docker Engine and Compose;
   - a `deploy` user with no password and **not** in the `docker` group, whose sudo allows exactly
     `scorecode-deploy` and `scorecode-ctl`;
   - `/opt/scorecode`, the daily log archive, and ufw rules for 22/80/443 (written, not enabled).
3. **The deploy account's own key** (never root's): `ssh-keygen -t ed25519 -f ~/.ssh/scorecode_deploy`,
   then `remote.sh root add-key < ~/.ssh/scorecode_deploy.pub`. Test: the key logs in as `deploy` and is
   refused as root; `sudo -l` lists the two programs only; `docker ps` is refused.
4. **Settings:** `python3 infra/ops/push-env.py` sends the operator's values over SSH stdin to the
   root-owned renderer (`env/*.env`, mode 600; `secrets/alertmanager.yml`). Database passwords and app
   keys are generated on the server, once, and never leave it. Re-run after changing a value.
5. **Registry:** `printf %s "$GHCR_READ_TOKEN" | remote.sh deploy ctl registry-login "$GHCR_USERNAME"`
   (a token that can only read packages, on stdin).
6. **Origin certificate** (the key is made on the server and stays there):
   `remote.sh deploy ctl make-csr | python3 infra/ops/cloudflare.py sign-csr | remote.sh deploy ctl install-cert`.
7. **Gate (a), with the owner's approval:**
   - `remote.sh root firewall-on`;
   - `remote.sh root harden-ssh`: keys only, root by key only. **It reverts itself in 3 minutes**: test a
     NEW login for root and deploy, check a password is refused, then `remote.sh root confirm-ssh`.
   - Recovery if locked out: the provider's browser console.
8. **GitHub:** the `production` environment, limited to `v*` tags, with secrets `DEPLOY_HOST`,
   `DEPLOY_USER` (`deploy`), `DEPLOY_SSH_KEY` (the deploy key) and `DEPLOY_KNOWN_HOSTS` (from
   `ssh-keygen -F`), each set from stdin. Variable `PRODUCTION_DOMAIN` only after the DNS cut-over.
   Required reviewers need a paid plan for a private repository; a tag push is the approval.
9. **First deploy:** push a tag (Release, below). Then `python3 infra/ops/create-admin.py` creates the
   first platform user and writes its TOTP enrolment to a private file on the Mac.
10. **Cloudflare (gate b):** `cloudflare.py dns-plan`, then `dns-apply --yes`, then `ssl-strict --yes`
    ("Full (strict)" and "Always Use HTTPS").

## Release
1. Merge to `main` with CI green. The release rehearsal (`release.yml`) runs on every change to the
   deploy files.
2. `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `release.yml` builds the four images, scans them (fixable critical vulnerabilities stop it) and pushes
   them to GHCR.
4. It deploys over SSH as `deploy`, which runs `sudo scorecode-deploy vX.Y.Z`: the server pulls that
   version's bundle image and runs its `infra/ops/deploy.sh`:
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
- **By hand**, from the operator's Mac:
  `infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl rollback vPREVIOUS`
  (`sudo scorecode-ctl versions` lists the releases kept on the server, the last five). It runs the same
  deploy as a release: a backup first, then the earlier images from GHCR. Migrations are expand-only, so
  the earlier code runs on the newer schema. Roll forward the same way with the newer version.
- **If a release corrupted data:** this is not a rollback, it's a restore
  ([backup-and-restore.md](backup-and-restore.md)), from the backup `deploy.sh` took just before.

## DNS cut-over (gate b) and its rollback
Before: the release is healthy (`scorecode-ctl status`, `smoke`), the smoke test passes from outside
against the VPS address with Cloudflare's Origin CA (`SMOKE_CONNECT_TO=<vps>:443 SMOKE_CACERT=origin-ca.pem`,
never `curl -k`), and a rollback has been drilled.

1. `cloudflare.py dns-list`: write down what the apex points at now (2026-10-14: two A records to
   Spaceship's parking page, `54.149.79.189` and `34.216.117.25`).
2. `cloudflare.py dns-apply --yes --replace=<those addresses>`: the apex points at the VPS (proxied);
   `*`, `admin` and `verify` are created. Email records (Brevo DKIM, DMARC, the `brevo-code` TXT,
   `send.*`) are other names or types and are never touched.
3. `cloudflare.py ssl-strict --yes`: "Full (strict)", Always Use HTTPS, TLS 1.2 minimum.
4. From outside, through Cloudflare: `SMOKE_BASE_DOMAIN=<domain> SMOKE_SCHEME=https infra/ops/smoke.sh`;
   `curl -sI http://<domain>/` answers 301 to https; the certificate chain verifies normally.
5. `gh variable set PRODUCTION_DOMAIN --body <domain>`: every later deploy smoke-tests through Cloudflare.

**Rollback** (a serious failure after the switch): point the apex back with `dns-apply`'s update in the
Cloudflare dashboard, or remove the four records; Cloudflare applies it within seconds (records are
proxied, so no client caches the VPS address). The application itself rolls back with `ctl rollback`.
