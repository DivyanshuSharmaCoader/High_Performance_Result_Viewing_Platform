# Complete platform verification

A step-by-step way to check every ScoreCode feature yourself, in order, on the live service, with
fictional data. The current state and its evidence are in
[the audit report](../reports/2026-10-16-platform-audit.md). Record each result in
[acceptance-checklist.md](acceptance-checklist.md).

## How to read this guide
- **Where:** 🖥️ **Mac Terminal** (Applications → Utilities → Terminal) · 🌐 **Browser** (Chrome or
  Safari) · ☁️ **Dashboard** (AWS, Cloudflare, Hostinger, Sentry, Brevo, in a browser) · 🛟 **Hostinger
  web console** (hPanel → VPS → Browser terminal; only for recovery).
- **Safety tag** on each test:
  - `READ-ONLY`: changes nothing.
  - `TEST DATA`: writes fictional data in your test school.
  - `EMAIL`: sends one email to an address you own; it counts against the daily email budget.
  - `PROD CHANGE`: touches the running service; read the note first.
  - `COST`: uses billable requests or storage, always a fraction of a cent here; see the note.
- **Outcome:** write PASS, FAIL, BLOCKED or NOT TESTED in the checklist. PASS only when you saw the
  expected result yourself.
- **Never** paste a password, code, key or token into a command, a chat or a screenshot. Commands that
  need secrets load them through `infra/ops/with-secrets.sh`, which never prints them.
- **Test data rules:** fictional names only (the samples below use "Test Student 001"…). Leave students'
  email column empty, so publishing sends no student emails. Staff invitations go only to addresses
  you own (with Gmail you can use `you+staff1@gmail.com`).
- **Shell:** the Mac's default shell is zsh. Paste each block as it is; lines starting with `#` are
  comments.

---

## Part A — Preflight (do this first, every time)

### PRE-01 Open the project and confirm it is the right one · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && git remote get-url origin && git branch --show-current && git log --oneline -1 && git status --short | wc -l
```
**Expect:**
- `.../High_Performance_Result_Viewing_Platform.git`
- branch `claude/scorecode-design-docs-ffo0a1`
- a commit line
- `0` uncommitted files

**If it fails:** "No such file" means the folder moved; find it with Finder → search for "ResultHub".
**Record:** the commit shown.

### PRE-02 Check the secrets file is complete (names only) · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh check; echo "exit code: $?"
```
**Expect:** every `required` line says `ok`, then `exit code: 0`. `BACKUP_S3_ENDPOINT` and the two
`TELEGRAM_` names may say MISSING; they're optional.
**If it fails:**
- `must be readable by you only`: run `chmod 600` on the file, as the message says.
- `MISSING` or `PLACEHOLDER` on a required name: fill it in your secrets file with a text editor.

### PRE-03 Which release is running, and is it healthy? · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl status && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl versions
```
**Expect:**
- `deployed: v0.1.4` (or newer);
- `api`, `postgres`, `proxy` and `redis` say `(healthy)`, and the others say `Up`;
- `versions` lists earlier releases, which are what rollback uses.

**If it fails:** `Permission denied` means the deploy key `~/.ssh/scorecode_deploy` is missing or was
removed on the server. `Operation timed out` means the server or network is down: open the Hostinger
web console (🛟).

### PRE-04 Public smoke test (no secrets needed) · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && SMOKE_BASE_DOMAIN=scorecode.website SMOKE_SCHEME=https SMOKE_TENANT= infra/ops/smoke.sh; echo "exit code: $?"
```
**Expect:** eight `ok` lines, `smoke: all checks passed`, `exit code: 0`. Certificates are checked
normally (no `-k`).
**If it fails:** `unreachable` on every line means DNS or Cloudflare (see OBS-02); a single wrong status
names the failing part.

### PRE-05 Provider logins work, nothing is written · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- uv run --project backend python infra/ops/secrets-check.py --connect cloudflare smtp ghcr ssh 2>&1 | grep -E "^connection|INVALID|MISSING"
```
**Expect:** `connection cloudflare: OK`, `smtp: OK`, `ghcr: OK`, `ssh: OK`.
**Known on 2026-10-16:** `ssh: CONNECTION FAILED (key not accepted)`. That check uses root, and
root's key no longer works; the `deploy` account (PRE-03) does. Fix: SEC-12.

### PRE-06 What these tests will never do
None of the commands here deploy a release, change DNS, delete production data or backups, or create a
paid resource. Commands that do touch the service carry `PROD CHANGE`, with a note on what happens and
how to undo it. Don't run anything not written here against production.

---

## Part B — Public website

### WEB-01 Homepage and navigation · 🌐 · `READ-ONLY`
1. Open `https://scorecode.website`.
2. Click every link in the header and footer.

**Expect:** each page loads with no error box; the padlock shows a valid certificate.
**Record:** any broken link (its text and where it was).

### WEB-02 Plans page and live plan data · 🌐 + 🖥️ · `READ-ONLY`
1. 🌐 Open the plans/pricing page from the homepage.
2. 🖥️ Fetch the live plan list:
   ```bash
   curl -sS --max-time 20 https://scorecode.website/api/v1/plans | python3 -m json.tool | grep -E '"(code|name|max_students|max_staff)"'
   ```

**Expect:** plans Free (150 students), Starter (600), Growth (2,000) and Pro (5,000), the same as the page
shows.
**Note:** there is **no online payment**: plans are assigned in the platform console (PLAN-03).

### WEB-03 Phone layout · 🌐 · `READ-ONLY`
Open the homepage, a school's login page (after ONB-01) and the student portal (after STU-04) on your
phone.
**Expect:** no sideways scrolling, readable text, and buttons you can tap.

### WEB-04 Error pages · 🌐 · `READ-ONLY`
Open `https://scorecode.website/this-page-does-not-exist` and `https://no-such-school-xyz.scorecode.website`.
**Expect:** a friendly "not found" page, never a stack trace or a blank page.

---

## Part C — Platform console (ScoreCode staff)

### PLAT-01 First sign-in with two-step · 🌐 · **do this first**
**Needs:** the file `~/Desktop/ScoreCode-console-2FA.txt` (made 2026-10-14), an authenticator app (Google
Authenticator, Microsoft Authenticator, 1Password…), and the `PLATFORM_ADMIN_EMAIL` and
`PLATFORM_ADMIN_PASSWORD` you set in your secrets file.
1. Open the enrolment file in TextEdit. Add it to your authenticator, either from the QR/URL or by typing
   the setup key shown there. Don't copy it anywhere else.
2. Open `https://admin.scorecode.website/login`.
3. Sign in with the email and password, then the 6-digit code.
4. Once in, **delete the enrolment file**: drag it to the Bin and empty it.

**Expect:** the console with Tenants, Plans, Health and Audit.
**If it fails:**
- "invalid code": check the phone's clock is automatic.
- "invalid credentials": the password in the secrets file was changed after the account was created on
  2026-10-14. **The console has no password reset yet** (no endpoint or command); tell Claude, who will
  propose a supported reset. Don't edit the database.

**Record:** PASS/FAIL, and confirm the file is deleted.

### PLAT-02 Console health page · 🌐 · `READ-ONLY`
Console → **Health**.
**Expect:** database, cache, storage and queue all reported healthy.

### PLAT-03 Tenants list and detail · 🌐 · `READ-ONLY`
Console → **Tenants** → your test school (after ONB-01).
**Expect:** its plan, usage and status.

### PLAT-04 Suspend and reactivate the test school · 🌐 · `TEST DATA`
Console → Tenants → test school → **Suspend** (type the address, give a reason).
**Expect:**
- Signing in to `https://<test-school>.scorecode.website` now shows "temporarily unavailable".
- Existing sessions are signed out.
- **Reactivate** restores everything, with nothing lost.

**Never** do this to a real school during this check.

### PLAT-05 Closing a school (two approvals) · 🌐 · `TEST DATA` · optional, at the end
1. In the test school: Settings → **Your data** → *Close the account…* (owner only).
2. Expect a notice that nothing changes for 30 days, and *Cancel closure* is offered.
3. Cancel it. A real erasure test needs the 30 days to pass.

**Cleanup for the whole test:** suspend the test school (PLAT-04) when you're done, or request closure
and approve erasure in the console after 30 days. Never delete rows by hand.

---

## Part D — School onboarding

### ONB-01 Sign up a test school · 🌐 · `TEST DATA` `EMAIL`
**Needs:** an email address you own.
1. Open `https://scorecode.website/signup`.
2. Fill it in:
   - name: Test School One;
   - type: school;
   - address: `test-school-1` (if taken, add a number);
   - your email;
   - a strong password (12+ characters, not used elsewhere).
3. Submit. **Expect:** "check your email".
4. Open the email from ScoreCode (`results@scorecode.website`) and click the link.

**Expect:**
- You land signed in on `https://test-school-1.scorecode.website/admin`, with a setup checklist.
- The plan is Free.

**If it fails:**
- No email within 5 minutes: check spam, then COM-01.
- "link expired": sign up again.

**Record:** the school address you chose; later steps call it `<test-school>`.

### ONB-02 Second test school (for isolation tests) · 🌐 · `TEST DATA` `EMAIL`
Repeat ONB-01 with `test-school-2` and a second address you own (e.g. `you+school2@gmail.com`).

### ONB-03 Institution settings · 🌐 · `TEST DATA`
`<test-school>` → **Settings → Institution**: official name, address, contact email, language (try
Hindi). Save.
**Expect:** saved; the marksheet later shows these.

### ONB-04 Branding and logo · 🌐 · `TEST DATA`
Settings → **Branding**: upload a small PNG logo and pick a colour.
**Expect:** the logo and colour show on the login page and in the portal. A file that isn't an image,
or is too large, is refused with a message.

### ONB-05 Export the school's data · 🌐 · `TEST DATA`
Settings → **Your data** → *Export everything* (owner only).
**Expect:** a ZIP becomes available within minutes; it opens as CSV files, and the download link expires
after 7 days.

---

## Part E — Accounts and sign-in

### AUTH-01 Wrong password is refused · 🌐 · `READ-ONLY`
Sign out, then sign in to `<test-school>` with a wrong password.
**Expect:** a generic "email or password is wrong", which never says which one.

### AUTH-02 Repeated failures lock the account for a while · 🌐 · `READ-ONLY`
Five wrong passwords in a row for the same account (`login_max_failures = 5`).
**Expect:** a "too many attempts" message. Even the right password is refused for 15 minutes
(`login_lockout_minutes`), then works. Use the second school's owner, not your main account, and don't
script this against production.

### AUTH-03 Sessions are per school · 🌐 · `READ-ONLY`
Signed in to `test-school-1`, open `https://test-school-2.scorecode.website/admin`.
**Expect:** the login page of school 2; you are not signed in there.

### AUTH-04 Sign out everywhere · 🌐 · `READ-ONLY`
Account → **Sign out everywhere** → confirm.
**Expect:** another browser or phone signed in to the same account is signed out on its next click.

### AUTH-05 Sensitive actions ask for your password again · 🌐 · `TEST DATA`
Approve results (RES-07), or start closing the account, more than 10 minutes after signing in
(`reauth_window_minutes = 10`).
**Expect:** you are asked for your password (and two-step code) first.

### AUTH-06 Turn on two-step sign-in · 🌐 · `TEST DATA`
Account → **Two-step sign-in** → scan → enter a code → save the recovery codes somewhere safe.
**Expect:** your next sign-in asks for a code.

### AUTH-07 Recovery code works once · 🌐 · `TEST DATA`
Sign in using one recovery code instead of the app code. Then try the same recovery code again.
**Expect:** the first works; the second is refused.

### AUTH-08 An admin resets a colleague's two-step (never the owner's) · 🌐 · `TEST DATA`
**Needs:** STU-05 (an invited admin).
Staff → that admin → *Reset two-step*.
**Expect:** it works for them. The same option is not offered for the owner.

### AUTH-09 Password reset by email · 🌐 · `EMAIL`
Sign out → *Forgot password* → your email.
**Expect:**
- an email with a link;
- setting a new password works;
- the old password no longer works;
- the link doesn't work a second time.

An unknown email gets the same "check your email" answer (no account discovery).

---

## Part F — Academic structure and grading

### ACAD-01 Session and terms · 🌐 · `TEST DATA`
**Structure** → Sessions → add `2026-27` with Term 1 and Term 2 → make it current.

### ACAD-02 Department, programme, cohort · 🌐 · `TEST DATA`
Structure: add department `Test Department`, programme `Test Programme`, and cohort code `TEST-10A`
in 2026-27.

### ACAD-03 Courses · 🌐 · `TEST DATA`
Structure → Courses: add `TST101 Test Mathematics` and `TST102 Test Science`, with credits 4 and 3.

### ACAD-04 Grading scheme · 🌐 · `TEST DATA`
1. **Grading** → New from template (*school bands*, or *10-point credit scale (SGPA)*) → preview with a few
   marks → save → set as default.
2. Edit it.

**Expect:** the edit creates a new version, and the preview shows the grades you expect.

---

## Part G — Students and staff

### STU-01 Import students (valid file) · 🖥️ + 🌐 · `TEST DATA`
1. 🖥️ Make a fictional file on your Desktop (writes `~/Desktop/scorecode-test/`):
   ```bash
   mkdir -p ~/Desktop/scorecode-test && python3 - <<'EOF'
   import csv, pathlib
   out = pathlib.Path.home() / "Desktop" / "scorecode-test"
   rows = [(f"TST{n:03d}", f"Test Student {n:03d}", "TEST-10A") for n in range(1, 21)]
   with open(out / "students-valid.csv", "w", newline="") as f:
       w = csv.writer(f); w.writerow(["Enrollment no.", "Full name", "Cohort"]); w.writerows(rows)
   bad = [("TST900", "", "TEST-10A"), ("TST001", "Duplicate Of One", "TEST-10A"), ("TST901", "Unknown Cohort", "NO-SUCH")]
   with open(out / "students-invalid.csv", "w", newline="") as f:
       w = csv.writer(f); w.writerow(["Enrollment no.", "Full name", "Cohort"]); w.writerows(rows[:2] + bad)
   print("wrote", out / "students-valid.csv", "and", out / "students-invalid.csv")
   EOF
   ```
2. 🌐 **Imports** (or Students → Import) → students → upload `students-valid.csv` → check the mapping →
   commit.

**Expect:** 20 students in cohort TEST-10A.

### STU-02 Import students (invalid file is rejected) · 🌐 · `TEST DATA`
Upload `students-invalid.csv`.
**Expect:**
- nothing is saved;
- the report lists the empty name (TST900), the duplicate of TST001 and the unknown cohort (NO-SUCH),
  each with its reason;
- *Download report* gives an XLSX.

Then cancel the import.

### STU-03 Activation codes · 🌐 · `TEST DATA`
Students → **Activation codes** → cohort TEST-10A → generate/print.
**Expect:** a slip per student with a one-time code. Note TST001's code.

### STU-04 A student activates and signs in · 🌐 (private window) · `TEST DATA`
1. Open a private window → `https://<test-school>.scorecode.website/activate`.
2. Enter enrollment `TST001`, its code and a new password.
3. Sign in.

**Expect:** the student portal (no results yet). The same code can't be used twice.

### STU-05 Invite staff · 🌐 · `TEST DATA` `EMAIL`
**Staff** → Invite → `you+admin1@gmail.com` as *Institution admin*, and `you+faculty1@gmail.com` as
*Faculty*.
**Expect:** two emails; accepting each one sets a password and signs the person in.

### STU-06 Roles limit what staff can do · 🌐 · `TEST DATA`
Sign in as the faculty member.
**Expect:**
- the menu shows only Marks entry for assigned papers;
- `https://<test-school>.scorecode.website/admin/staff` shows "not allowed";
- deactivating that faculty member (as owner) signs them out on their next click.

---

## Part H — Exams, marks, results, publication

### RES-01 Create an exam · 🌐 · `TEST DATA`
**Exams** → New: `Test Term 1 Exam`, session 2026-27, Term 1, cohort TEST-10A, the default grading
scheme.

### RES-02 Papers and components · 🌐 · `TEST DATA`
1. Add papers TST101 and TST102, each with components *Internal 40* and *Final 60*, minimum 33 to pass.
2. Assign the faculty member to TST101.

### RES-03 Marks entry by faculty · 🌐 · `TEST DATA`
1. Exam → *Open marks entry*.
2. As faculty: **Marks entry** → TST101 → type marks for a few students → submit.
3. Open the same sheet in two windows, change one mark in each, and save both.

**Expect:**
- marks save as you type;
- a mark above the maximum is refused;
- the second save warns that someone else changed it; it never silently overwrites.

### RES-04 Marks import (valid) · 🌐 · `TEST DATA`
1. **Imports → Marks** → the exam → *All papers* → download the template. It's pre-filled with the
   students.
2. Fill marks for everyone in Numbers or Excel; use `AB` for one absent student. Save as XLSX or CSV.
3. Upload it.

**Expect:** clean, with a row count; commit.

### RES-05 Marks import (invalid is rejected) · 🌐 · `TEST DATA`
Change one mark to `75` in a 60-mark component, one enrollment number to `TST999`, and one cell to `xyz`.
Upload.
**Expect:** nothing is saved, and each problem is listed with its row. Cancel the import.

### RES-06 Process and preview · 🌐 · `TEST DATA`
1. Exam → close marks entry. Unsubmitted papers ask for a reason.
2. Results → **Process**.

**Expect:**
- totals, grades and pass/fail match what you'd calculate by hand for two students;
- anomalies are listed;
- processing again gives identical results.

### RES-07 Approve · 🌐 · `TEST DATA`
Results → **Approve** (password again).
**Expect:** marks lock, and editing a mark is refused.

### RES-08 Publish now · 🌐 · `TEST DATA`
Results → **Publish now**.
**Expect:**
- the status is live;
- marksheet progress counts up to 20 of 20 ready, about a minute for 20 students;
- no student emails are sent, because the students have no email address.

### RES-09 The student sees their own result only · 🌐 (TST001's window) · `READ-ONLY`
**Expect:**
- the result, with grade and totals, under latest result and history;
- class statistics only as your settings allow;
- no other student's details anywhere.

### RES-10 Marksheet PDF download · 🌐 · `READ-ONLY`
As TST001 → the result → *Download marksheet*.
**Expect:** a PDF with your school's name and logo, the marks, a QR code and a verification code.

### RES-11 Verify a marksheet publicly · 🌐 · `READ-ONLY`
Open `https://verify.scorecode.website/v`, enter the code from the PDF (or scan the QR with your phone).
**Expect:** "valid", with masked details (no full date of birth, no marks beyond what the page shows).
Then enter a made-up code. **Expect:** "can't be checked here".

### RES-12 Withdraw and publish again · 🌐 · `TEST DATA`
Results → **Withdraw** (password, reason).
**Expect:**
- the student no longer sees it;
- verifying the PDF says *Withdrawn*;
- publishing again creates version 2.

### RES-13 Correct a published result · 🌐 · `TEST DATA`
Results → *Correct results…* (reason, password) → change TST002's mark → process → approve.
**Expect:**
- the correction preview lists only TST002, old against new;
- *Publish corrected results* shows TST002 the new result;
- the old marksheet verifies as *Superseded*.

---

## Part I — Communication

### COM-01 A test email through the running app · 🖥️ · `EMAIL` `PROD CHANGE` (sends one email)
Sends one plain email to your `ALERT_EMAIL_TO` address (read from the secrets file, never printed):
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- bash -c 'printf "%s\n" "$ALERT_EMAIL_TO" | infra/ops/server/remote.sh deploy ctl email-test'
```
**Expect:**
- `accepted by the SMTP provider; message id <...>`;
- within a few minutes, an email "ScoreCode email test" in that inbox (check spam).

**If it fails:**
- `authentication`: the SMTP key; recheck with PRE-05.
- `daily email budget is spent`: wait for the time given.

### COM-02 Brevo's own record · ☁️ · `READ-ONLY`
Brevo → Transactional → Logs (or Statistics).
**Expect:** the messages from COM-01, ONB-01 and AUTH-09 as *Delivered*.
**Note:** the free plan allows 300 a day; ScoreCode keeps itself to 280 in any 24 hours.

### COM-03 In-app notification on publish · 🌐 · `READ-ONLY`
As TST001, after RES-08.
**Expect:** a notification bell entry linking to the result.

---

## Part J — Plans and money

### PLAN-01 Plan & usage page · 🌐 · `READ-ONLY`
`<test-school>` → **Plan & usage**.
**Expect:** Free, with 20 of 150 students used, staff and storage usage.

### PLAN-02 A limit is enforced · 🌐 · `TEST DATA`
1. Console → the test school → **Plan** → set a temporary override `max_students = 25` (or use the Free
   plan's 150 with a larger file).
2. Import a file with 10 more students.

**Expect:** a clear message that the plan's limit is reached, with nothing half-imported.
Remove the override afterwards.

### PLAN-03 Change plan in the console · 🌐 · `TEST DATA`
Console → test school → **Change plan** → Starter.
**Expect:** the school's Plan & usage shows Starter and 600 students. Set it back to Free.

### PLAN-04 Feature gating · 🌐 · `READ-ONLY`
On Free, look for a paid-plan feature: two-step approval (Settings) or custom branding beyond the basics.
**Expect:** marked as needing a higher plan, not broken.

### PLAN-05 One free trial · 🌐 · `TEST DATA`
Plan & usage → *Start my free trial* (30-day Pro).
**Expect:** Pro limits. A second trial for the same school is refused. Revoke it in the console
afterwards (Tenants → trial → revoke).

### PLAN-06 Payments · status: **not implemented**
There is no online payment, invoice or GST handling in ScoreCode (decision D17). To charge a school
today: agree the plan, take payment outside the product, set the plan in the console (PLAN-03) and issue
an invoice yourself. See LEG-04 before charging.

---

## Part K — Background jobs, cache, storage

### JOB-01 Queue is healthy · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl jobs stats
```
**Expect:** `no due, running or dead jobs`, or only recent queued ones.

### JOB-02 Failed marksheets can be retried · 🌐 · `READ-ONLY`
After RES-08: Results → marksheets.
**Expect:** all ready. If any failed, *Retry failed marksheets* is shown and fixes them.

### JOB-03 Worker restart is harmless · 🖥️ · `PROD CHANGE` (the worker restarts, about 10 s; no data lost)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl restart worker && sleep 15 && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl status | grep -E "deployed|worker"
```
**Expect:** the worker is `Up` again; queued work continues; JOB-01 shows nothing dead.

### JOB-04 Redis down, slow database · isolated only
Don't do these on production. They run in CI's load workflow (`perf.yml`, chaos `redis` and `dbslow`),
and reports are in `benchmarks/results/`. Ask Claude to run `perf.yml` with the chaos input if you
want fresh evidence. It uses GitHub Actions minutes, not your server.

### STO-01 File storage as the app uses it · 🖥️ · `COST` (one tiny object written and deleted in R2; free tier)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl storage-test
```
**Expect:** six `ok` lines: write, read back, signed link (HTTP 200), unsigned link refused, tampered
link refused, delete. No URL is printed.

### STO-02 A marksheet link expires · 🌐 · `READ-ONLY`
As TST001, right-click *Download marksheet* → copy the link. Open it in another browser after 6 minutes.
**Expect:** refused (expired). Signed links last 5 minutes (`signed_url_ttl_s = 300`).

### STO-03 One school can't fetch another's files · 🌐 · `READ-ONLY`
**Needs:** ONB-02 and a published result in school 2 (repeat RES-01 to RES-08 there, briefly).
Signed in to school 1, open school 2's marksheet download address
(`https://test-school-2.scorecode.website/api/v1/me/results/<id>/marksheet`, with the id from school 2's
address bar).
**Expect:** 401/403/404, never a PDF.

---

## Part L — Backups and restore

### BAK-01 Nightly backups exist · 🖥️ · `READ-ONLY` `COST` (one LIST request)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- uv run --project backend python - <<'EOF'
import os, boto3
s3 = boto3.client("s3", region_name=os.environ["BACKUP_S3_REGION"], aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["BACKUP_S3_SECRET_ACCESS_KEY"])
objs = sorted(s3.list_objects_v2(Bucket=os.environ["BACKUP_S3_BUCKET"], Prefix="prod/db/").get("Contents", []), key=lambda o: o["LastModified"])
print(len(objs), "backups; total", sum(o["Size"] for o in objs), "bytes")
for o in objs[-3:]: print(o["LastModified"].strftime("%Y-%m-%d %H:%M UTC"), o["Size"], "bytes")
EOF
```
**Expect:** a backup from last night (21:00 UTC, 02:30 IST), each a few hundred KB today.

### BAK-02 A backup on demand · 🖥️ · `PROD CHANGE` `COST` (adds one encrypted dump, about 0.3 MB)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl backup 2>&1 | grep -E '"backup"|error|warning' | sed -E 's#s3://[^/]+#s3://<bucket>#'
```
**Expect:** one JSON line with `"backup":"s3://<bucket>/prod/db/..."`, `bytes`, `sha256`.

### BAK-03 The key file is right (no decryption) · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- sh -c 'k="$HOME/.scorecode/backup-age-key.txt"; stat -f "mode %Lp" "$k" && [ "$(age-keygen -y "$k")" = "$BACKUP_AGE_RECIPIENT" ] && echo MATCH || echo MISMATCH'
```
**Expect:** `mode 600` and `MATCH`.

### BAK-04 Synthetic decryption check · 🖥️ · `READ-ONLY`
Proves your key decrypts something encrypted to it, without touching any real backup. It makes a
throwaway file, encrypts it to the backups' public key, decrypts it with your key, and compares:
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- sh -c 'd=$(mktemp -d); printf "scorecode synthetic restore check\n" > "$d/p"; age -r "$BACKUP_AGE_RECIPIENT" -o "$d/p.age" "$d/p" && age -d -i "$HOME/.scorecode/backup-age-key.txt" "$d/p.age" | cmp - "$d/p" && echo "DECRYPT OK" || echo "DECRYPT FAILED"; rm -rf "$d"'
```
**Expect:** `DECRYPT OK`.

### BAK-05 Full restore test of the newest production backup · 🖥️ · **critical** · `PROD CHANGE` (a throwaway database on the server for about a minute; the live database is only read)
The 2026-10-15 attempt hung and then failed to decrypt. The script has since been rewritten to check
each step and say where it stops (BAK-03 and BAK-04 first).
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- uv run --project backend python infra/ops/restore-test.py ~/.scorecode/backup-age-key.txt; echo "exit code: $?"
```
**Expect, in order:**
- `1/4 key: ...matching the backups' recipient`
- `2/4 backup: scorecode-....dump.age, ... sha256 matches`
- `3/4 decrypted here: a PostgreSQL dump`
- the server lines `received ... dump; starting a scratch database` and `{"restored":"/restore/db.dump",...,"forced_rls_tables":47,...}`
- `fingerprint: N of N lines identical`, or a few `live:`/`restored:` lines for sessions, jobs or
  mail_sends written since the backup
- `4/4 server: restore test finished`, then `exit code: 0`

**If it fails:** the `STOP:` line says why:
- **key / mode / recipient:** fix the key file (BAK-03).
- **checksum:** the download was corrupted; run it again.
- **decryption failed:** the message is age's own reason.
- **didn't finish within 30 minutes:** the server was busy or unreachable (PRE-03).

The live database is never written. The scratch database has no network and is removed even on
failure.
**Record:** the `fingerprint:` line and any differing lines (they show table names and counts only).

### BAK-06 The server's backup key can't delete · 🖥️ · `READ-ONLY` (asks to delete an object that doesn't exist)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- uv run --project backend python - <<'EOF'
import os, boto3
from botocore.exceptions import ClientError
s3 = boto3.client("s3", region_name=os.environ["BACKUP_S3_REGION"], aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["BACKUP_S3_SECRET_ACCESS_KEY"])
for key in ("prod/db/does-not-exist.age", "restore-test/does-not-exist", "_healthcheck/does-not-exist"):
    try: s3.delete_object(Bucket=os.environ["BACKUP_S3_BUCKET"], Key=key); print(key, "DELETE ALLOWED  <-- not expected")
    except ClientError as e: print(key, "delete:", e.response["Error"]["Code"])
EOF
```
**Expect:** `AccessDenied` three times. (If a delete were ever allowed, it would only leave a harmless
"delete marker" for an object that never existed, and you should tell Claude: the key is too powerful.)

### BAK-07 Lifecycle rules apply to the right prefixes · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- uv run --project backend python - <<'EOF'
import os, boto3
s3 = boto3.client("s3", region_name=os.environ["BACKUP_S3_REGION"], aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["BACKUP_S3_SECRET_ACCESS_KEY"])
b = os.environ["BACKUP_S3_BUCKET"]
o = max(s3.list_objects_v2(Bucket=b, Prefix="prod/db/")["Contents"], key=lambda x: x["LastModified"])
h = s3.head_object(Bucket=b, Key=o["Key"])
print("newest prod backup", o["LastModified"].strftime("%Y-%m-%d"), "->", h.get("Expiration"), "| versioned:", bool(h.get("VersionId")))
EOF
```
**Expect:** `rule-id="scorecode-prod-retention-35d"`, an expiry date 35 days later, and
`versioned: True`.
**Note:** the two 1-day rules were checked on 2026-10-14 with probe objects; the backup key can't read
the rule definitions themselves (BAK-08).

### BAK-08 Noncurrent versions and rule filters · ☁️ AWS console · `READ-ONLY`
S3 → the backup bucket → **Management** → Lifecycle rules. Open each rule.
**Expect:**
- `scorecode-prod-retention-35d`: prefix `prod/`; current versions expire after 35 days; noncurrent
  after 1 day.
- `scorecode-restore-test-1d` and `scorecode-healthcheck-1d`: prefixes `restore-test/` and
  `_healthcheck/`; 1 day. **Check they also expire noncurrent versions** (1 day) and clean up expired
  delete markers; otherwise those small objects stay forever.
- No rule without a prefix: a bucket-wide rule could expire everything.

### BAK-09 Spending alerts · ☁️ AWS console · `READ-ONLY`
1. Billing → **Budgets**: a monthly cost budget (e.g. $1) with an email alert to you.
2. Billing → **Billing preferences**: *Receive Free Tier usage alerts* on.

**Note:** budgets warn; they don't stop charges. ScoreCode's own alert `ScoreCodeBackupStorageHigh` emails
you when backups pass 4 GB.

---

## Part M — Security and privacy

### SEC-01 One school's session doesn't work at another school · 🌐 · `READ-ONLY`
Signed in as the owner of school 1, open `https://test-school-2.scorecode.website/api/v1/admin/students`.
**Expect:** `401`. Sessions are bound to one school's address.

### SEC-02 A record ID from school 1 can't be read in school 2 · 🌐 · `READ-ONLY`
1. In school 1, open a student and copy the ID from the address bar (`/admin/students/<id>`).
2. Sign in to school 2 as its owner, then open
   `https://test-school-2.scorecode.website/api/v1/admin/students/<that id>`.

**Expect:** `404`. The database filters every table to the signed-in school (row-level security);
`backend/tests/integration/test_isolation.py` checks this for every endpoint in CI.

### SEC-03 A student can't use staff endpoints · 🌐 · `READ-ONLY`
As TST001, open `https://<test-school>.scorecode.website/api/v1/admin/students`.
**Expect:** `403`.

### SEC-04 No session, no data · 🖥️ · `READ-ONLY`
Type your test school's address when asked:
```bash
printf 'Test school address (e.g. test-school-1): '; read -r SLUG; for p in /api/v1/me /api/v1/admin/students /api/v1/me/results; do curl -sS --max-time 15 -o /dev/null -w "%{http_code} $p\n" "https://$SLUG.scorecode.website$p"; done
```
**Expect:** `401` three times.

### SEC-05 Forms need the CSRF token · 🖥️ · `READ-ONLY`
```bash
curl -sS --max-time 15 -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" -d '{"login_id":"nobody@example.org","password":"not-a-real-one"}' https://scorecode.website/api/v1/auth/login
```
**Expect:** `403` (refused before any password check). Measured 2026-10-16: 403.

### SEC-06 Security headers · 🖥️ · `READ-ONLY`
```bash
curl -sS --max-time 20 -o /dev/null -D - https://scorecode.website/ | grep -i -E "^(strict-transport-security|content-security-policy|x-content-type-options|x-frame-options|referrer-policy|permissions-policy)" | cut -c1-90
```
**Expect:** all six present; `x-frame-options: DENY`; HSTS `max-age=31536000`.

### SEC-07 HTTPS, certificate, redirect, old TLS refused · 🖥️ · `READ-ONLY`
```bash
curl -sS --max-time 15 -o /dev/null -w "http -> %{http_code} %{redirect_url}\n" http://scorecode.website/; echo | openssl s_client -connect scorecode.website:443 -servername scorecode.website 2>/dev/null | openssl x509 -noout -subject -issuer -enddate; curl -sS --max-time 15 --tlsv1.1 --tls-max 1.1 -o /dev/null https://scorecode.website/ 2>/dev/null && echo "TLS 1.1 ACCEPTED (not expected)" || echo "TLS 1.1 refused (expected)"
```
**Expect:**
- `http -> 301 https://scorecode.website/`;
- `subject=CN=scorecode.website`, a Let's Encrypt issuer, an end date in the future;
- `TLS 1.1 refused`.

### SEC-08 Uploads take only real spreadsheets · 🌐 · `TEST DATA`
Rename a picture (`.png`) to `test.xlsx` and upload it as a student import.
**Expect:** refused with a readable reason, and nothing imported.

### SEC-09 No secret value is in the repository · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- python3 infra/ops/leak-scan.py; echo "exit code: $?"
```
**Expect:** every name `not found`, `exit code: 0`. It searches all history and prints names, never
values. Result 2026-10-16: clean.

### SEC-10 Audit logs · 🌐 · `READ-ONLY`
School → **Audit log**.
**Expect:** your imports, approvals, publications, withdrawals and corrections, each with who, when and
why. There's no way to edit or delete an entry. Console → **Audit** shows ScoreCode staff actions.

### SEC-11 Monitoring and internal ports aren't public · 🖥️ · `READ-ONLY`
```bash
curl -sS --max-time 15 -o /dev/null -w "/metrics answers %{http_code} as %{content_type}\n" https://scorecode.website/metrics; cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- sh -c 'for p in 22 80 443 3000 5432 6379 8000 9090 9093; do nc -z -G 5 "$DEPLOY_HOST" $p >/dev/null 2>&1 && echo "port $p open" || echo "port $p closed"; done'
```
**Expect:**
- `/metrics` answers as `text/html` (the web app's own page), not metrics;
- on the server, only 22 and 443 are open.

### SEC-12 SSH is keys-only, and root can be recovered · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- sh -c 'ssh -o BatchMode=yes -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive -o ConnectTimeout=10 root@"$DEPLOY_HOST" true 2>&1 | tail -1; ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -i "$DEPLOY_SSH_KEY_FILE" root@"$DEPLOY_HOST" true 2>/dev/null && echo "root key: works" || echo "root key: refused"'
```
**Expect:** `Permission denied (publickey)` (passwords are off), then `root key: works`.
**Known 2026-10-16:** `root key: refused`. To restore it:
1. Hostinger hPanel → VPS → **SSH keys** → add the text of `~/.ssh/scorecode_vm.pub`, the `.pub` file:
   the public half only.
2. Or 🛟 web console as root → `nano /root/.ssh/authorized_keys` → paste that one line → Ctrl-O, Enter,
   Ctrl-X.

Never paste a file without `.pub`: that's a private key.

---

## Part N — Monitoring and operations

### OBS-01 Health endpoints · 🖥️ · `READ-ONLY`
```bash
for p in /healthz /readyz /api/v1/plans; do curl -sS --max-time 15 -o /dev/null -w "%{http_code} %{time_total}s $p\n" "https://scorecode.website$p"; done
```
**Expect:** `200` three times, each under 2 s.

### OBS-02 DNS and Cloudflare settings · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py dns-list && infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py settings
```
**Expect:**
- A records for `scorecode.website`, `*`, `admin` and `verify`, each `proxied=True`;
- the Brevo DKIM, DMARC, `send` and `brevo-code` records present;
- `ssl strict`, `always_use_https on`, `min_tls_version 1.2`.

**Never** run `dns-apply` or `ssl-strict` while verifying.

### OBS-03 Logs: structured and free of personal data · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl logs api 30
```
**Expect:**
- JSON lines with method, path, status and duration;
- no passwords, tokens, cookies, marks or student names.

### OBS-04 Sentry receives a scrubbed error · 🖥️ + ☁️ · `PROD CHANGE` (one synthetic error; the free plan allows 5,000 a month)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl sentry-test
```
**Expect:** `Sentry answered HTTP [200] (accepted)`. Then ☁️ Sentry → Issues → the newest *ScoreCode
Sentry test*:
- the text reads `student [email], phone [phone], enrollment [number], marks [n], token [token]`;
- there's no user, cookies or request body.

PASS only after you've looked.

### OBS-05 Alert emails arrive · ✉️ inbox · `READ-ONLY`
Search the `ALERT_EMAIL_TO` inbox (and spam) for **ScoreCodeTestAlert**, sent 2026-10-14 at about
10:57 UTC; Brevo accepted it.
**Expect:** found.
A fresh test alert needs root on the server: **BLOCKED** until SEC-12 is fixed. Then ask Claude for one.

### OBS-06 Time sync and the log-archive timer · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- sh -c 'ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$HOME/.ssh/scorecode_deploy" deploy@"$DEPLOY_HOST" "timedatectl show -p NTPSynchronized --value; timedatectl timesync-status | grep Server; systemctl list-timers scorecode-logs.timer --no-pager | head -2"'
```
**Expect:**
- `yes`;
- a server from `samay1.nic.in`, `samay2.nic.in` or `time.nplindia.org`;
- the timer, with its next run.

### OBS-07 Disk, memory, swap · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- sh -c 'ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$HOME/.ssh/scorecode_deploy" deploy@"$DEPLOY_HOST" "df -h / | tail -1; free -m | sed -n 1,3p; uptime"'
```
**Expect:** disk under 80% used; swap 2 GB with little used; load under 1.5 when idle.
Measured 2026-10-16: 9%, swap 0, load 0.17.

---

## Part O — Releases and recovery

### DEP-01 CI is green on the deployed code · 🖥️ · `READ-ONLY`
```bash
cd ~/Desktop/ResultHub && gh run list --branch claude/scorecode-design-docs-ffo0a1 --limit 6 --json headSha,name,conclusion --jq '.[]|[.headSha[0:7],.name,.conclusion]|@tsv'
```
**Expect:** the newest commit shows CI, Ops and Release `success`.

### DEP-02 Images are private · 🖥️ · `READ-ONLY`
```bash
curl -sS --max-time 15 -o /dev/null -w "anonymous pull: HTTP %{http_code}\n" "https://ghcr.io/token?scope=repository:divyanshusharmacoader/scorecode-backend:pull&service=ghcr.io"
```
**Expect:** `401`.

### DEP-03 API restart recovers · 🖥️ · `PROD CHANGE` (the API restarts: about 15 s of errors for anyone using it)
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl restart api && sleep 20 && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl status | grep -E "^api"
```
**Expect:** `api ... (healthy)`. Measured 2026-10-14: healthy again after 14 s.

### DEP-04 Rollback drill · 🖥️ · `PROD CHANGE` — **decide first; only at a quiet time**
It deploys the previous release, then the current one again. Each switch:
- takes about a minute, with a few seconds unavailable;
- takes a backup first (`COST`: about 0.3 MB).

Drilled 2026-10-14 (v0.1.3 → v0.1.2 → v0.1.3: 59 s and 58 s, smoke passing). Step 1:
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl rollback v0.1.3 && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl smoke
```
Step 2, back to the current release:
```bash
cd ~/Desktop/ResultHub && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl rollback v0.1.4 && infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl status | head -1
```
**Expect:** smoke passes after step 1; step 2 ends with `deployed: v0.1.4`.

### DEP-05 Migration rollback · **NOT TESTED**
Every release so far has the same schema (migration 0022 is the newest). The rule is expand-only
migrations, so an older release runs on a newer schema. A real drill needs a release that adds a
migration; plan it then. In CI, `test_migrations.py` runs every migration up, down and up again.

### DEP-06 How a release happens (read only)
`docs/runbooks/deploy-and-rollback.md`:
1. Push a `v*` tag.
2. `release.yml` rehearses, builds, scans, pushes to private GHCR, takes a backup and deploys as `deploy`.
3. It rolls back on its own if the smoke test fails.

Never tag during verification.

---

## Part P — Capacity

### PERF-01 What has been measured (read)
- `benchmarks/results/2026-10-14-result-day-vps.md`: **200 students at once on this server, 0 errors**,
  p95 under 0.65 s on every page; marksheets at about 2.1 a second (8,000 in about an hour).
- `benchmarks/results/2026-10-14-result-day-ci-2vcpu.md`: 1,000 at once on a similar 2-vCPU runner,
  with 3–6% of requests refused.
- **Nothing above 200 is shown to work on this server.**

### PERF-02 Re-run the 200-student step on the server · 🖥️ · `PROD CHANGE` — **BLOCKED** while root SSH is refused (the script connects as root)
A separate test stack runs beside production for about 40 minutes. Production stays up, guarded by
memory and CPU-steal watchdogs. Run it at a quiet hour:
```bash
cd ~/Desktop/ResultHub && STUDENTS=2000 VUS=200 HOLD=2m RUNS="B:preauth:1 B:cold:1" infra/ops/with-secrets.sh run -- benchmarks/vps/remote-loadtest.sh
```
**Expect:** `failed 0.00%` in both summaries; results in `benchmarks/results/runs-vps/runs/`.

### PERF-03 Find the ceiling (400, then 600) · plan, not runnable yet
It needs k6 on another machine, so the load generator doesn't share the server's CPU. Until then, keep
early schools within the measured 200 students using it at once.

### PERF-04 Marksheet throughput in your own test · 🌐 · `READ-ONLY`
During RES-08, note how long *20 of 20 marksheets ready* takes.
**Expect:** 10–20 s.

---

## Part Q — Commercial and legal readiness

### LEG-01 Documents that exist (all DRAFT)
`docs/legal/`:
- terms of service, privacy notice, school data processing agreement;
- refund and cancellation, acceptable use, grievance contact;
- the readiness matrix.

None is published in the product, and none is final.

### LEG-02 Controls already in the product
Evidence for each is in the readiness matrix:
- isolation between schools;
- TLS everywhere, and backups encrypted with a key that never reaches the server;
- records of processing kept a year;
- closure with a 30-day grace and two-approval erasure;
- full data export;
- logs kept a year in India;
- NIC/NPL time;
- the incident runbook (CERT-In 6 hours);
- no advertising or profiling of children's data.

### LEG-03 Decisions for you
- The legal entity that signs contracts.
- The grievance officer's name and contact.
- Whether backups stay in Sydney or move to Mumbai (same storage price; matrix L8a).
- A paid email plan once a school larger than about 220 students wants email notices.

### LEG-04 Before charging money (with a CA)
- GST registration;
- the invoice format;
- TDS deducted by schools;
- place of supply (matrix T1–T4);
- how payment is taken: the product has no checkout.

### LEG-05 For an Indian lawyer
Questions L1–L14 in `docs/legal/readiness-matrix.md`, especially:
- L3: the children's-data exemption;
- L7: per-student erasure versus records a school must keep;
- L8 and L8a: foreign processors and backups.

Then the DPA and privacy notice, before the first school signs.
