# Credentials for deployment (P16.1–P16.3)

Everything the deployment needs lives in **one file on the owner's laptop**:

    /Users/divyanshusharma/.scorecode/scorecode.env      (directory 700, file 600, outside the repository)

The template, with every variable, why it's needed, and a fake example of its shape, is
[`infra/ops/secrets.env.example`](../../infra/ops/secrets.env.example).

## How the values are used without being seen
- **Only one way in.** Tooling reads the file through [`infra/ops/with-secrets.sh`](../../infra/ops/with-secrets.sh):
  - `check` prints variable **names** with ok, MISSING or PLACEHOLDER.
  - `run -- <command>` gives the values to one command through its environment.
- **Read literally.** The file is never sourced or executed as shell, so nothing in it can run.
- **Nothing printed.** Values are never printed, logged or written to the repository. On the server they
  go into `env/*.env` files (mode 600), generated over SSH from the environment.
- **Blocked for the assistant.** Claude Code's user settings (`~/.claude/settings.json`) deny the
  assistant's file tools, and shell commands that print files, under `~/.scorecode`. Both were tested and
  refused.
- **Generated on the server, never asked for:** database passwords, the app's secret and abuse keys, the
  Grafana password, and the CI deploy key pair (its private half goes straight into a GitHub secret).

## What the owner provides (and why)
| Group | Variables | For |
|---|---|---|
| Domain, Cloudflare | `SCORECODE_DOMAIN`, `CLOUDFLARE_API_TOKEN` (one zone; DNS, SSL and Certificates, Zone Settings: Edit; Zone: Read), `CLOUDFLARE_ZONE_ID` | DNS records, the origin certificate, "Full (strict)" and "Always Use HTTPS" (P16.1) |
| Server | `DEPLOY_HOST`, `DEPLOY_SSH_USER`, `DEPLOY_SSH_PORT`, `DEPLOY_SSH_KEY_FILE` (a **path**, never the key) | Installing Docker, the firewall, a `deploy` user; deploying (P16.2) |
| File storage | `FILES_S3_*` (Cloudflare R2 recommended) | Marksheet PDFs, logos, uploads |
| Backups | `BACKUP_S3_*` (a second provider or region), `BACKUP_AGE_RECIPIENT` (the **public** key only) | Nightly encrypted backups (P16.4) |
| Email | `SMTP_*`, `MAIL_FROM` | Result notices, invitations, resets, security notices, alerts |
| Alerts | `ALERT_EMAIL_TO`; optional `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Who gets paged (P16.5) |
| First platform user | `PLATFORM_ADMIN_EMAIL`, `PLATFORM_ADMIN_NAME`, `PLATFORM_ADMIN_PASSWORD` | The console account. Its TOTP enrolment is written to `~/.scorecode/platform-admin-totp.txt` for the owner |
| Registry | `GHCR_USERNAME`, `GHCR_READ_TOKEN` (`read:packages` only), or make the packages public | The server pulls release images (P16.3) |
| Optional | `SENTRY_DSN` | Error reports |

## Asked for at the time, not stored in the file
Each is a one-time approval in the conversation, or a notification if the owner is away:
1. Setting the GitHub repository secrets and creating the `production` environment, with the owner as
   required reviewer.
2. Changing Cloudflare zone settings (SSL mode, Always Use HTTPS) and adding DNS records.
3. Running setup commands with sudo on the new server (Docker, firewall, users).
4. Pushing the first version tag, which publishes images to GHCR and starts a release.

## Giving the access up afterwards
When deployment work is done, the loader is also put behind approval: an `ask` rule (or `deny`) for
`Bash(*with-secrets.sh*)` in `~/.claude/settings.json`. From then on, any use of the file needs the
owner's permission at that moment. To remove all access immediately, add that rule yourself, or move the
file.

## Limits, stated plainly
- **The rules bind the assistant's tools, not the operating system.** The loader runs as you, so it can
  read the file. That's how the values reach commands. The protection is that it prints nothing.
- **What a command does with the values is the command's business.** The values reach only the commands
  the deployment scripts run: ssh, the Cloudflare API, `gh secret set`.
- **Never paste a secret into the chat.** Put it in the file. If one was pasted somewhere it shouldn't
  have been, rotate it ([security-incident.md](security-incident.md)).
