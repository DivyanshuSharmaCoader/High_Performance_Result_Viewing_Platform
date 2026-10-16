# Test evidence: training videos

Everything below was run, not assumed. "Recorded" means a Playwright run on GitHub Actions drove the
real application (the full `docker compose --profile app` stack, with a fresh database and Mailpit
for email). Every beat's action carries assertions on what the screen then shows. The application
under test is this repository at the commit named; **production was not touched.**

## 1. The recording run the videos are made from

**Run [38953541522](https://github.com/DivyanshuSharmaCoader/High_Performance_Result_Viewing_Platform/actions/runs/38953541522)**
on commit `84385cf` (branch `claude/scorecode-design-docs-ffo0a1`), 16 October 2026: **14 passed, 0
failed**, in 23.7 minutes. The modules ran in story order (M01 last, so that its tour shows a school
that is already set up):

| Order | Module | Result | Time |
|---|---|---|---|
| 1 | m02-create-portal | ✓ | 1.9 min |
| 2 | m03-academic-structure | ✓ | 2.4 min |
| 3 | m04-grading | ✓ | 1.7 min |
| 4 | m05-students | ✓ | 2.1 min |
| 5 | m06-staff | ✓ | 1.4 min |
| 6 | m07-student-activation | ✓ | 1.1 min |
| 7 | m08-exam-setup | ✓ | 1.8 min |
| 8 | m09-marks-entry | ✓ | 2.3 min |
| 9 | m10-results | ✓ | 2.2 min |
| 10 | m11-student-result | ✓ | 1.5 min |
| 11 | m12-plan-settings | ✓ | 1.7 min |
| 12 | m13-audit-export | ✓ | 1.2 min |
| 13 | m14-troubleshooting | ✓ | 1.3 min |
| 14 | m01-orientation | ✓ | 1.3 min |

The run's artifact (`training-recordings-38953541522`, kept 14 days) holds the 14 WebM recordings,
their timelines, and the marksheet PDF that Module 11 downloaded.

**The marksheet PDF** (`m11-marksheet-SPS1001.pdf`), opened and read: Sunrise Public School,
"Statement of marks", Periodic Test 1 — October 2026, Aarav Sharma, SPS1001, Class 10 · Section A.
Mathematics 88 (Internal 36/40, Written 52/60) A2, Science 84 A2, English 83 A2, Hindi 78 B1,
Social Science 79 B1, all Pass. Total 412 / 500, 82.4%, grade A2, grade point 8.6, Passed. It has a QR
code, a verification address and a code. Every component mark matches what was entered on camera
(Mathematics, Science) or off camera (the other three).

## 2. What each recording asserts

The full list is in [VIDEO_PLAN.md](VIDEO_PLAN.md#what-each-module-shows-and-the-check-the-recording-makes),
and the code in `frontend/training/specs/school.spec.ts`. A few of the values the application
computed itself (none were typed into the video):

| Module | Shown, as computed by ScoreCode |
|---|---|
| M05 | The student check found exactly the three planted mistakes: "Name is missing", "Enrollment number SPS1003 is also on row 3", and "Cohort "10B" doesn't exist in 2026-27". After the fix: "5 new students will be added." |
| M08 | Each paper: "Internal 40 + Written 60 = 100". Mathematics: "10A: Amit Kumar"; the others: "10A: admins only" |
| M09 | Aarav's Mathematics total 88. The 65-out-of-60 entry: "Written: Out of 60". The Science file: "SCI10 Internal: 45 is outside 0–40"; after the fix, "Saves marks for 6 students: 6 new." |
| M10 | 6 students: 4 pass, 2 fail; pass rate 66.7%, average 70.1%. Aarav: 82.4%, grade A2, 412 / 500. "Processed before every paper was submitted" (ENG10, HIN10, SCI10, SST10) |
| M11 | The verification page: Valid; student "Aa*** Sh***", enrollment "SP***01"; no marks; the SHA-256 fingerprint of the marksheet |
| M13 | The audit log's before/after of Amit Kumar's marks entries; a ready export (CSV) |

## 3. Earlier runs: what failed, and what changed

Each failure was a mismatch between the recording and the real application. In three cases, marked
**narration**, the application behaved differently from what the script said, so the **narration**
was corrected to match the application, not the other way round.

| Run | Commit | Result | Cause | Fix |
|---|---|---|---|---|
| 38933423915 | e9a358e | failed to start | Workflow file: an unquoted colon in a step name | Quoted (d3f8503) |
| 38933687257 | d3f8503 | M02 ✓, M03 ✗ | "Structure" matched two links (sidebar and checklist) | Scoped to the main navigation |
| 38935549722 | eccae25 | M02 ✓, M03 ✗ after 15 min | The button is "New session", not "New academic session"; no action timeout | Label fixed; a 20 s action timeout added. **Narration**: "Make this the current session" is already ticked for a first session, so the script no longer says to tick it |
| 38939035571 | 57f072f | M02 ✓, M03 ✗ | "Term 1" matched two cells | First match |
| 38939863659 | e0b1a7b | M02–M03 ✓, M04 ✗ | Grade "A1" is an input's value, not text | Points at the "Band 1 grade" field. **Narration**: the first scheme is the default automatically, so the script no longer says to make it default |
| 38941867302 | bf44572 | M02–M03 ✓, M04 ✗ | "Band 1 grade" also matched "Band 1 grade points" | Exact match |
| 38942873436 | a2d90a6 | M02–M05 ✓, M06 ✗ | The first "Amit Kumar" on the page was the hidden phone layout | Visible matches only |
| 38944485167 | 901febb | M02–M11 ✓, M12 ✗ | "Usage" heading also matched "Plan & usage" | Exact headings |
| 38947149853 | af13ef1 | **all 14 ✓** (23.6 min) | — | Its frames showed date fields as mm/dd/yyyy and a static Module 1, so it was recorded again |

Before any recording, the scripts were also checked against the code. **Narration**: Module 10's
"Worth a look" originally mentioned low marks and absences. The application flags neither (it flags
missing marks, no marks, full marks everywhere, absent from every paper, withheld, changed since
processing, and unsubmitted papers), so the line was rewritten.

## 4. Media checks (`build.py check`)

Run on the final files, 17 October 2026 (IST): **28 of 28 ok**.

```
ok   RENDERED/en/m01-orientation.mp4: 75s, h264 1920x1080, mean -16.6 dB, max -1.3 dB
ok   RENDERED/en/m02-create-portal.mp4: 107s, h264 1920x1080, mean -16.5 dB, max -1.3 dB
ok   RENDERED/en/m03-academic-structure.mp4: 135s, h264 1920x1080, mean -16.5 dB, max -1.1 dB
ok   RENDERED/en/m04-grading.mp4: 95s, h264 1920x1080, mean -16.9 dB, max -1.3 dB
ok   RENDERED/en/m05-students.mp4: 119s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/en/m06-staff.mp4: 74s, h264 1920x1080, mean -16.6 dB, max -1.4 dB
ok   RENDERED/en/m07-student-activation.mp4: 65s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/en/m08-exam-setup.mp4: 98s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/en/m09-marks-entry.mp4: 128s, h264 1920x1080, mean -16.5 dB, max -1.2 dB
ok   RENDERED/en/m10-results.mp4: 122s, h264 1920x1080, mean -16.6 dB, max -1.3 dB
ok   RENDERED/en/m11-student-result.mp4: 84s, h264 1920x1080, mean -16.7 dB, max -1.2 dB
ok   RENDERED/en/m12-plan-settings.mp4: 92s, h264 1920x1080, mean -16.4 dB, max -1.2 dB
ok   RENDERED/en/m13-audit-export.mp4: 64s, h264 1920x1080, mean -16.6 dB, max -1.3 dB
ok   RENDERED/en/m14-troubleshooting.mp4: 78s, h264 1920x1080, mean -16.4 dB, max -1.3 dB
ok   RENDERED/hi/m01-orientation.mp4: 75s, h264 1920x1080, mean -16.6 dB, max -1.2 dB
ok   RENDERED/hi/m02-create-portal.mp4: 107s, h264 1920x1080, mean -16.6 dB, max -0.7 dB
ok   RENDERED/hi/m03-academic-structure.mp4: 135s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/hi/m04-grading.mp4: 95s, h264 1920x1080, mean -16.3 dB, max -1.4 dB
ok   RENDERED/hi/m05-students.mp4: 119s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/hi/m06-staff.mp4: 74s, h264 1920x1080, mean -16.5 dB, max -1.1 dB
ok   RENDERED/hi/m07-student-activation.mp4: 65s, h264 1920x1080, mean -16.4 dB, max -1.3 dB
ok   RENDERED/hi/m08-exam-setup.mp4: 98s, h264 1920x1080, mean -16.8 dB, max -1.2 dB
ok   RENDERED/hi/m09-marks-entry.mp4: 128s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/hi/m10-results.mp4: 122s, h264 1920x1080, mean -16.7 dB, max -1.3 dB
ok   RENDERED/hi/m11-student-result.mp4: 84s, h264 1920x1080, mean -16.6 dB, max -1.2 dB
ok   RENDERED/hi/m12-plan-settings.mp4: 92s, h264 1920x1080, mean -16.6 dB, max -0.9 dB
ok   RENDERED/hi/m13-audit-export.mp4: 64s, h264 1920x1080, mean -16.8 dB, max -1.3 dB
ok   RENDERED/hi/m14-troubleshooting.mp4: 78s, h264 1920x1080, mean -16.7 dB, max -1.2 dB
```

Checked for every file: a video stream (H.264, 1920×1080), an AAC audio stream, an embedded subtitle
stream (`mov_text`, language tagged `eng` or `hin`), loudness (mean −16.3 to −16.9 dB after EBU R128
normalisation to −16 LUFS, then a −1 dB limiter; the highest peak in any file is −0.7 dB). Every file's audio is
AAC at 48 kHz, and that the last subtitle ends inside the video.

## 5. Frames inspected

A contact sheet (one frame 2.5 s into every narrated beat) was made for every module and looked at.
In each, the screen matches what that beat's narration describes, and the orange pointer and box sit
on the element being named. The final sheets (from run 38953541522) were reviewed for all 14 modules. Details worth noting:
- The date fields show dd/mm/yyyy (01/04/2026 to 31/03/2027). An earlier run showed mm/dd/yyyy,
  because Playwright's headless shell carries only US English; the recordings now use full Chromium
  in an Indian locale.
- A few beats catch the page between two screens (a loading skeleton) at the sampled moment; the
  following frames show the finished page.

## 6. The player

`PLAYER/index.html` was opened in a browser (served by `tools/serve.py`) and tested by script:
- the first module loads (`RENDERED/en/…mp4`, 1920×1080), with its English subtitle track showing;
- after seeking to 40 s and choosing हिंदी: the source became `RENDERED/hi/…mp4`, the position stayed
  at 40 s, the subtitle track became Hindi and showed the Hindi line for that moment, and the page
  heading, labels and module titles switched to Hindi (`<html lang="hi">`);
- after switching back at 75 s: English source, 75 s kept, English subtitle line showing.

After the final render, every module was loaded in both languages from the player's own list (28
loads): each gave the right file (`RENDERED/<lang>/<module>.mp4`), 1920×1080, the duration above,
and a showing subtitle track in that language with one cue per narrated beat. In a real playback test
of Module 10 (Hindi from 60 s), switching to English mid-play kept playing from the same moment
(62 s, then 63.4 s) with the English line for that moment. Reaching the end moved on to Module 11,
which started playing. Hindi (Devanagari) subtitles render in the video.

The page's module titles, heading and labels switch language. The "who" and "plan" lines under the
video come from the scripts' `role` and `plan` fields, which are in English only.

## 7. Not verified, or limits

- **Listening.** No person has listened to the narration yet. The audio was checked by measurement
  (duration per beat, loudness, no clipping), not by ear. The voices are macOS's built-in Rishi
  (Indian English) and Lekha (Hindi), which read English words inside Hindi sentences with a Hindi
  accent. A Hindi speaker should watch at least one module before the series is shared.
- **Hindi text** was written for this series and has not been reviewed by a native speaker.
- **Prices on screen.** Module 12 shows the app's Compare plans table, which includes the
  catalogue prices. The narration doesn't read them, but they are visible. If prices change,
  re-record Module 12.
- **Compare plans lists two features that don't exist yet.** The app's own table shows "Your own
  domain" and "Integration API" among Pro features, but neither is implemented (VERIFIED_FEATURE_MATRIX,
  code only). The videos never mention or demonstrate them, but they are visible in that table.
  This is a product issue, not a video one.
- **Off camera.** In Module 9, English, Hindi and Social Science marks are saved through the
  application's API after the recording stops, as the narration says ("entered the same way"). The
  Science import and the Mathematics grid are on camera.
- The test passwords and activation codes visible in the videos exist only on the throwaway
  recording stack, which is deleted when the run ends.
