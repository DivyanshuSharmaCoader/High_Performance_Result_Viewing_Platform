# Completion report: ScoreCode school training videos

17 October 2026.

## Delivered

| Asked for | Delivered | Where |
|---|---|---|
| Real, playable training videos in English and Hindi | 14 modules × 2 languages = 28 MP4s, 1920×1080 H.264, AAC 48 kHz narration, embedded subtitles; 22 min 16 s per language | `RENDERED/en`, `RENDERED/hi` (made locally; not in git, 133 MB) |
| Synchronised narration and subtitles | One beat-timed recording per module carries both languages; SRT and WebVTT for each | `CAPTIONS/` |
| A bilingual player with a language selector that really works | English / हिंदी switch that swaps video, subtitles and page text, and keeps the playback position; auto-advances to the next module | `PLAYER/index.html` (serve with `tools/serve.py`) |
| Inspect the real app first; verified feature matrix | Roles, plans, enforced and code-only features, by area, with how each was verified | `VERIFIED_FEATURE_MATRIX.md` |
| Fictional Sunrise Public School, 2026–27, Periodic Test 1, Class 10-A, five subjects, the named people | All of it, mapped onto ScoreCode's four real roles | `VIDEO_PLAN.md` |
| 14 modules, orientation to the end-to-end workflow | M01–M14 | `VIDEO_PLAN.md` |
| Test every demonstrated workflow; no fabrication | Each recording asserts what its narration says; the final run passed 14 of 14 on the real application | `TEST_EVIDENCE.md` |
| Scripts, recordings, audio | `SCRIPTS/` (in git); `RECORDINGS/`, `AUDIO/` (local) | — |
| Index by role, task and feature | ✓ | `INDEX.md` |
| Troubleshooting guide | Real messages from the code, with fixes | `TROUBLESHOOTING.md` |
| Media verification and playback | `build.py check` (28 / 28 ok); 28 loads and a playback test in a browser; a contact sheet of every beat reviewed | `TEST_EVIDENCE.md` §4–6 |
| No production data changes | All recordings used a throwaway stack in GitHub Actions. Production was not contacted | — |

## Where the application and the brief differed

- **Roles.** ScoreCode has four school roles: Owner, Administrator, Faculty and Student. The principal
  is shown as the Owner, and the examination coordinator and office administrator as Administrators.
  There is **no parent login**: Module 11 says so, and Mr. Anil Sharma appears only in narration.
- **"Written 60 + Internal 40".** The app's preset is "Internal 40 + External 60"; Module 8 renames
  External to Written on camera.
- **CBSE.** The 9-band scale is ScoreCode's "CBSE-style" starting template, not official CBSE policy,
  and the videos don't claim otherwise.
- **Off camera.** English, Hindi and Social Science marks are saved through the application's API
  after Module 9's recording stops, as its narration says.
- **Not demonstrated, on purpose.** Features listed in plans but not built (custom domain, API
  access, marksheet templates, advanced analytics, years of history); payments (there are none);
  starting the one-time free trial (shown, not started); prices (not read out).

## Needs a person before the videos are shared

1. **Listen** to at least one module in each language. The audio was checked by measurement only.
   The voices are macOS's Rishi and Lekha.
2. **Hindi review** of the scripts and subtitles by a native speaker.
3. **Prices on screen.** Module 12 shows the app's Compare plans table, prices included. Approve
   that, or re-record Module 12 if prices change.
4. **Product finding.** That same table lists "Your own domain" and "Integration API", which aren't
   implemented. Worth fixing in the app.

## How to rebuild

See [README.md](README.md). One CI run (about 25 minutes) records all 14 modules; assembly on the Mac
takes about 12 minutes.
