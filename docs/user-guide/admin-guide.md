# Administrator guide

For the people who run results at an institution. What you see depends on your role:
- The **owner** can do everything, including transferring ownership.
- An **administrator** can do everything except billing ownership.
- An **exam controller** runs exams and results.

Menus you can't use are hidden.

## 1. Getting started
1. **Sign up** at the ScoreCode site. Your institution gets its address straight away, and every new
   institution may start **one** 30-day Pro trial (Plan & usage → *Start my free trial*). Nothing is
   charged, and when the trial ends nothing is deleted: you go back to your plan's limits.
2. **Protect your account:** Account → **Two-step sign-in**. Scan the QR code with an authenticator app
   and keep the ten recovery codes somewhere safe. The dashboard reminds administrators until it's on.
3. **Settings → Institution:** official name, address, what students may see of class statistics
   (nothing, averages only, or full), and the **language for students and marksheets**: English, Hindi or
   Punjabi. In Hindi or Punjabi, students and parents read their results in that language (they can
   switch), and marksheets print English with that language beside it. **Settings → Branding:** logo and colours (on plans with custom
   branding).

## 2. Academic structure (Structure)
Build it once per year:
- Departments and programmes.
- **Sessions** (academic years), each with its **terms**. One session is *current*.
- **Cohorts** (sections or batches) in a session.
- **Courses** with credits. Credits are needed for SGPA schemes.

You can type them in, or import courses from a spreadsheet (Imports).

## 3. Grading (Grading)
Start from a template, such as *10-point credit scale (SGPA)*, *school bands* or *marks with ranks*,
and adjust the bands, pass rules and rounding.
- A scheme is **versioned**. The version an exam was processed with stays attached to it, so editing a
  scheme never changes published results.
- One scheme is your institution's default.

## 4. Students and staff (People)
- **Students → Import:**
  1. Download the template, fill in enrollment numbers, names and cohorts, and upload.
  2. Every row is checked first, with a readable reason for each problem, and nothing is saved until you
     confirm.
  3. Fix the file and upload it again.
- **Activation codes:** students create their own password with their enrollment number and a one-time
  code. Print slips per cohort (Students → Activation codes) and hand them out. Codes expire.
- **Staff → Invite:** an email invitation with a role. Faculty see only the papers you assign them.
  Removing someone signs them out everywhere and frees a seat. Their past work and audit history stay.
- **Two-step for staff:** administrators can reset a colleague's two-step sign-in (never the owner's).

## 5. An exam, from setup to publication (Exams)
1. **Create** the exam: name, term, kind (semester, term, unit test…), cohorts, grading scheme.
2. **Papers:**
   - Add a course and its components, e.g. *Internal 40* and *End semester 60*, with a minimum to pass
     where your rules have one.
   - Credits come from the course.
   - Assign faculty per paper and cohort.
3. **Open marks entry.** Marks come in two ways, and you can mix them:
   - **Faculty** enter them in the mark sheet. It saves as they type, and two people editing the same
     sheet never overwrite each other silently.
   - **Imports → Marks:**
     1. Choose the exam, then *All papers* or one paper.
     2. Download the template, which is pre-filled with every student. One file can carry every paper.
     3. Upload it. The check lists every problem (a mark above the maximum, a code it doesn't know, a
        student not in the exam, duplicates) and saves nothing until the file is clean.
   - **Attendance codes:** `AB` absent, `EX` exempt, `MP` malpractice, `WH` withheld.
4. **Close marks entry** when every paper is submitted. If a paper isn't, you can still process, but you
   must give a reason, and it is recorded.
5. **Results → Process.** Results are computed exactly as the scheme says. The preview shows the
   figures, anomalies (missing marks, unusual distributions) and each student's result exactly as they
   will see it.
   - Changed a mark? The preview turns *stale*. Process again.
   - Processing twice gives identical results.
6. **Approve.** You'll be asked for your password (and two-step code) again. Approving locks the marks.
   - With *two-step approval* (Settings, on plans that include it), a second administrator must
     approve.
7. **Publish:**
   - **Publish now:** students see their results within a second, and are told in the app and by email.
   - **Schedule:** pick a date and time, and it goes live by itself. You can cancel until then.
   - Every student's result is frozen at publication. Nothing anyone does later changes what was
     published.

## 6. After publication
- **Marksheets:**
  - A PDF for every student is prepared right after publication. The Results tab shows progress (*120
    of 120 marksheets ready*), and *Retry failed marksheets* is there if any failed.
  - Each PDF carries a verification code and QR code.
- **Withdraw** a publication that shouldn't be live, e.g. published too early or the wrong exam
  (password again, and a reason).
  - Students no longer see it, and its marksheets now verify as *Withdrawn*.
  - You can publish the same approved results again later. The new publication is the next version.
- **Correct results** when a mark was wrong after publishing (Results tab → *Correct results…*, with a
  reason and your password):
  - Students keep seeing the live version while you work. Nothing changes for them until you publish.
  - Change the marks (in the paper's mark sheet, or by uploading a corrected file), then process and
    approve as usual.
  - Before you publish, *Correcting published results* lists every student whose result changes, with
    the live result next to the corrected one.
  - *Publish corrected results* replaces the live version with the next version. Only the students whose
    result changed are notified, and the old marksheets' QR codes now say *Superseded*.
  - *Cancel correction* goes back to the live version, as long as no mark was changed (change it back
    first if needed). Withdrawing the live version is still possible during a correction.
- **Revoke one marksheet** (e.g. issued to the wrong person) from that student's row in the exam's
  Results.
- **Analytics:** pass rates, averages, median and spread per paper, grade distribution, and a comparison
  of sections.

## 7. Your data
- **Settings → Your data** (owner only): *Export everything* prepares a ZIP of CSV files with students,
  staff, structure, exams, every mark, every published result, verification codes and the audit log.
  Passwords and other secrets are never included.
- It takes a minute or two; download it with your password. Each export is kept seven days, then deleted.
  Up to five exports a day. Every request and download is in the audit log.
- **Close the account** (owner only, same page): asks for your password, a reason and your institution's
  address. Every administrator is emailed. For 30 days nothing changes: keep working, export, or *Cancel
  closure*. After that, ScoreCode staff confirm and all your institution's data is erased; encrypted
  backups expire within about a month. No fee and no notice period.

## 8. Keeping track
- **Audit log:** who did what and when, across everything above, with before and after values.
  Filterable, and it can't be edited by anyone.
- **Plan & usage:** students, staff, storage and publications this year against your plan's limits.
  Limits are checked when you act, with a clear message, never half-way through.

## Good practice
- Turn on two-step sign-in for every administrator.
- Publish from a reliable connection, and *schedule* when timing matters. A scheduled release prepares the
  marksheet PDFs beforehand; for several thousand students, schedule it at least half an hour ahead.
- Before a big result day, tell ScoreCode support the date and the number of students.
