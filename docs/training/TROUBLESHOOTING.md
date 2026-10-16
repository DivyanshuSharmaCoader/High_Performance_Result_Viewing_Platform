# Troubleshooting guide for schools

The messages in quotes are what ScoreCode shows, taken from the application's code. Module 14 shows
the first four on screen.

## Signing in

| What happens | Why | What to do |
|---|---|---|
| "Check your login details. After several wrong attempts an account is locked for a few minutes; you can also reset your password." | Wrong email, enrollment number or password; or too many attempts | Check the login and password. Wait a few minutes after several failures, or use **Forgot password?** |
| "Too many sign-in attempts." with a countdown | Many failed attempts from this device or network | Wait for the countdown to finish |
| Forgot password? sends nothing | The reset email only goes to an account **with an email address**. ScoreCode answers the same either way, so nobody can find out who has an account | Staff always have an email. For students, record an email address (Students, Edit) before they need it |
| A student without an email has forgotten their password | There is no self-service reset without email, and no administrator reset button for an activated account | Add the student's email so Forgot password? works. Otherwise contact ScoreCode support |
| "That code didn't match. Try the newest one." | The two-step sign-in code is out of date | Type the newest six-digit code; check the phone's clock is set automatically |

## Student activation

| What happens | Why | What to do |
|---|---|---|
| "That enrollment number and activation code don't match an account waiting for activation. Check the slip from your institution." | Wrong enrollment number or code, a code already used, or an expired one | Check both against the slip. If the slip is lost or old, an administrator opens the student and chooses **Replace activation code** |
| Activation codes cannot be issued to a student | The student already has an active account | They sign in with their enrollment number and password |
| The enrollment number can't be changed | It is the student's login once an account or activation code exists | Correct enrollment numbers before issuing codes |

## Students and imports

| What happens | Why | What to do |
|---|---|---|
| The import check lists rows with errors | Missing required columns (Enrollment no., Full name), a duplicate enrollment number, an unknown cohort code, and similar | Download the checked file, correct it, then **Upload fixed file**. Or import only the valid rows |
| A limit message on Students or Imports | The plan's limit (Free: 150 active students, 5,000 rows per import) | Plan & usage shows the numbers. Archive students who have left, or ask ScoreCode about another plan |
| A cohort is missing from the Add student list | Cohorts belong to a session, and the list shows the current session | Check Structure, Cohorts, and which session is current |

## Staff

| What happens | Why | What to do |
|---|---|---|
| The invitation email didn't arrive | Spam folder, a typo in the address, or an expired invitation | Check the address on the Staff page; the person's menu has **Resend invitation** |
| A limit message when inviting | Free allows 5 staff accounts, 2 of them administrators | Plan & usage shows the seats. **Disable account** (the person's menu) for people who have left frees their seat |

## Marks

| What happens | Why | What to do |
|---|---|---|
| A teacher sees "Nothing to mark right now" | Papers show only while marks entry is open, and only those assigned to them | An administrator opens marks entry (exam, Setup) and assigns the teacher (paper menu, Assign faculty) |
| A cell is red: "Out of 60" | The mark is more than the component's maximum | Correct it; wrong cells are not saved |
| "Enter a number, or AB, EX, MP or WH" | Text that is neither a mark nor an attendance code | AB absent, EX exempt, MP malpractice, WH withheld |
| "Someone else saved this row first. Your entry (…) was not saved." | Two people edited the same student at once | Their value is loaded. Check it and type again if needed |
| Submit paper is greyed out | Some student has neither marks nor an attendance code, or changes are still saving | Fill every row; wait for "All changes saved" |
| The sheet says "Read only" | The paper is submitted, entry is closed, or the results are approved | An administrator can return the paper, reopen entry with a reason, or revoke approval |
| Import from Excel is greyed out | Unsaved changes in the grid | Wait for "All changes saved" |

## Results

| What happens | Why | What to do |
|---|---|---|
| "Not every paper is submitted" | Some papers were entered by the office or not submitted by the teacher | Wait for teachers, or **Process results** and give the reason (recorded in the audit log) |
| "These results are out of date" | Marks changed after processing | Process again before approving |
| "Another administrator has to approve results you processed." | Two-person approval is on (Growth and Pro) | A second administrator approves |
| Schedule… is locked | Scheduled publication comes with Growth and Pro, or the free trial | Publish now, or ask ScoreCode about the plan |
| "Preparing marksheet PDFs…" for a long time | Large classes take a little while | Wait. Results are already visible to students, and the PDFs follow |
| A mistake found after publishing | — | **Withdraw** with a reason, or correct the marks and publish the corrected results. Old marksheets' QR codes then say they were superseded |

## Verification

| What happens | Why | What to do |
|---|---|---|
| The verification page says **Withdrawn** | The school withdrew those results | Ask the school for the current marksheet |
| "…isn't a verification code" | A mistyped code | Type the code exactly as printed, or scan the QR code |

## Getting help

The school's own contact (Settings, Contact) is shown to students. For ScoreCode itself, write to
support@scorecode.in.
