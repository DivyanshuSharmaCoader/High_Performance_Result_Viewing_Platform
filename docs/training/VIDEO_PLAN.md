# Video plan: ScoreCode school training (English and हिंदी)

One fictional school, **Sunrise Public School** (session 2026–27, Class 10, Section A, five subjects),
goes through one examination, **Periodic Test 1 — October 2026**, from signing up to a verified
marksheet. Every module is a screen recording of the real application (no mock-ups) with narration
and subtitles in both languages. Names, marks and addresses are made up; the recordings run on a
throwaway copy of the application in GitHub Actions, never on production.

## People in the story, and their ScoreCode role

| Person | Job at the school | ScoreCode role | Appears in |
|---|---|---|---|
| Mrs. Sunita Sharma | Principal; signed the school up | Owner | 2–5, 8, 10, 12–14 |
| Mr. Rajesh Verma | Office administrator | Administrator | not on screen: module 6 shows the Administrator choice; he would be invited the same way |
| Mrs. Neha Gupta | Examination coordinator | Administrator | not on screen: module 1 names the coordinator as an Administrator |
| Mr. Amit Kumar | Mathematics teacher | Faculty | 6, 8, 9, 13, 14 |
| Aarav Sharma (SPS1001) | Student, Class 10-A | Student | 5, 7, 9–11 |
| Priya Verma (SPS1002) and four classmates | Students, Class 10-A | Students (imported) | 5, 9, 10 |
| Mr. Anil Sharma | Aarav's father | none: ScoreCode has no parent login | 11 |

ScoreCode has exactly four school roles. There is no separate principal, coordinator or parent role,
and the videos say so (module 1, module 11).

## Modules

Lengths are the narration time (the longer of the two languages per beat, plus pauses); the final
video is about that long.

| # | English title | हिंदी शीर्षक | Who | Plan | Beats | Length |
|---|---|---|---|---|---|---|
| M01 | Welcome to ScoreCode | ScoreCode में आपका स्वागत है | Everyone | Every plan | 7 | ~1:04 |
| M02 | Create your school's portal | अपने स्कूल का पोर्टल बनाएँ | Owner | Every plan (a new portal starts on Free) | 12 | ~1:44 |
| M03 | Academic structure: session, class, section and subjects | Academic structure: सत्र, कक्षा, सेक्शन और विषय | Owner or Administrator | Every plan | 15 | ~2:09 |
| M04 | Choose your grading scheme | अपनी grading scheme चुनें | Owner or Administrator | Every plan | 9 | ~1:25 |
| M05 | Add and import students | विद्यार्थी जोड़ें और import करें | Owner or Administrator | Every plan (Free: 150 active students; 5,000 rows per import) | 14 | ~1:55 |
| M06 | Invite teachers and staff | शिक्षकों और स्टाफ़ को आमंत्रित करें | Owner or Administrator; the teacher accepts | Every plan (Free: 5 staff accounts, 2 administrators) | 9 | ~1:10 |
| M07 | A student activates their account | विद्यार्थी अपना account activate करता है | Student | Every plan | 8 | ~1:01 |
| M08 | Set up an exam | परीक्षा तैयार करें | Owner or Administrator | Every plan | 13 | ~1:34 |
| M09 | Enter and import marks | अंक भरें और import करें | Faculty (own papers); Owner or Administrator (any paper, imports) | Every plan | 16 | ~2:03 |
| M10 | Process, approve and publish results | Results बनाएँ, approve और publish करें | Owner or Administrator | Every plan (two-person approval and scheduling: Growth and Pro) | 12 | ~1:56 |
| M11 | What students see, and verifying a marksheet | छात्र क्या देखते हैं, और marksheet की जाँच | Student; anyone verifying | Every plan | 10 | ~1:21 |
| M12 | Plan, usage, settings and branding | Plan, usage, settings और branding | Owner; Owner or Administrator | Every plan (theme and login page: Starter and above) | 11 | ~1:27 |
| M13 | Audit log and data export | Audit log और data export | Owner or Administrator; export: Owner only | Every plan | 9 | ~1:00 |
| M14 | Common problems, and the whole year at a glance | आम समस्याएँ, और पूरा साल एक नज़र में | Everyone | Every plan | 8 | ~1:14 |

Total: about 21 minutes per language.

## What each module shows (and the check the recording makes)

Each recording **asserts** what it shows: if the application does not do what the narration says,
the recording fails and no video is made. The checks are in `frontend/training/specs/school.spec.ts`.

| # | Shows | The recording checks |
|---|---|---|
| M01 | Login page, the owner's dashboard, the menu | Sign-in lands on `/admin` |
| M02 | Sign-up form, portal address, email verification, the set-up checklist, the Free plan | The verification email arrives (Mailpit), the link signs the owner in, the checklist shows |
| M03 | Session 2026-27 (current), Term 1 and Term 2, program Class 10, cohort 10A, five courses | Each record appears in its table; "Course MATH10 created"; five course rows |
| M04 | New scheme from "9-band scale (CBSE-style)", the bands, pass mark, Try it, Make default | The scheme opens in the editor; the Default badge |
| M05 | Add student Aarav (cohort 10A), activation-code slip, a spreadsheet with three mistakes, the fixed file, import | Code format `XXXXX-XXXXX`; the check lists the errors; "5 new students will be added."; "Import complete"; seven table rows |
| M06 | Invite Amit Kumar as Faculty; he accepts from the email and sets a password | The invitation email arrives; accepting lands on Marks entry |
| M07 | Aarav activates with his slip, sees "No results yet", signs out | Lands on `/me` with "Hello, Aarav" |
| M08 | Exam "Periodic Test 1 — October 2026", Unit test, Term 1, cohort 10A, five papers of Internal 40 + Written 60, Amit assigned to Mathematics, marks entry opened | Paper total 100; five papers; "10A: Amit Kumar"; "Marks entry open" |
| M09 | Amit types marks, a 65-out-of-60 mistake and its fix, AB for absent, paste from Excel, autosave, Submit; the owner imports Science from a file with a mistake, fixes and saves | Total 88; "Written: Out of 60"; "All changes saved"; "Internal: 45 is outside 0–40"; "Marks saved". English, Hindi and Social Science marks are then entered through the same API **off camera**, which the narration says |
| M10 | Close entry, the unsubmitted-papers warning, process with a reason, summary, Worth a look, a student's preview, approve, the locked Schedule button (Free), Publish now, marksheets prepared | "Revision 1 · processed"; "Processed before every paper was submitted"; the preview contains SPS1001; approved; Schedule disabled; "Live since"; "marksheets are ready to download" |
| M11 | Aarav's notification, latest result, the full result, the portal in Hindi, the PDF download, the verification link, the public check | Notification text; result article; Hindi marksheet heading; a PDF named `Marksheet-SPS1001-…pdf`; the verify page says Valid and does not show the enrollment number |
| M12 | Plan & usage, usage meters, Compare plans, the trial offer (not started), Settings, Affiliation CBSE saved, Results policy, a logo upload, the locked theme | "Settings saved"; "Logo updated"; "Available on Starter and above" |
| M13 | Audit log filtered by Marks, by Amit Kumar, an entry's before and after, results and approval entries; the owner's full export | Entries listed under each filter; "What changed"; a ready export with Download |
| M14 | A wrong password, Forgot password, a wrong activation code, a teacher with nothing to mark, plan limits, the year in order | The lockout hint; the activation mismatch message; "Nothing to mark right now" |

## Production pipeline

1. `build.py narrate` (Mac): `say` voices Rishi (Indian English) and Lekha (Hindi) speak every beat;
   `SCRIPTS/durations.json` records how long each beat needs.
2. `training.yml` (GitHub Actions): a fresh copy of the full application, then Playwright runs the
   modules in order at 1440×810, waiting for each beat's narration; it uploads one WebM and one
   timeline per module.
3. `build.py assemble` (Mac): narration placed at each beat's recorded start, subtitles from the
   same times, scaled to 1920×1080, H.264/AAC MP4 with soft subtitles.
4. `build.py check`: every MP4 is read back (streams, resolution, loudness, narration inside the video).
5. `build.py player`: `PLAYER/index.html`.

## Not shown, on purpose

- Features listed in plans that have no working code: custom domain, API access, marksheet templates,
  advanced analytics, years of history (see VERIFIED_FEATURE_MATRIX).
- Payments: ScoreCode takes none; plan changes are by writing to ScoreCode.
- Prices: the Compare plans page shows them, but the narration does not read them out, so a price
  change does not make the videos wrong.
- Production data of any kind.
