# ScoreCode school training videos

Fourteen short videos, in **English** and **हिंदी**, that take a CBSE school from signing up to a
verified marksheet on the real application. They follow one made-up school, Sunrise Public School,
through Periodic Test 1 for Class 10, Section A.

| File | What it is |
|---|---|
| [COMPLETION_REPORT.md](COMPLETION_REPORT.md) | What was delivered, where the app differed from the brief, and what still needs a person |
| [VIDEO_PLAN.md](VIDEO_PLAN.md) | The modules, the people in the story, what each video shows and checks |
| [INDEX.md](INDEX.md) | Which videos to watch, by role, by task and by screen |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common problems, the exact messages, and what to do |
| [VERIFIED_FEATURE_MATRIX.md](VERIFIED_FEATURE_MATRIX.md) | What ScoreCode really does, by role and plan, and how each item was verified |
| [TEST_EVIDENCE.md](TEST_EVIDENCE.md) | The recording runs, the checks they made, and the media checks |
| `SCRIPTS/` | The narration of every module in both languages (`mNN-*.json`), and `durations.json` |
| `CAPTIONS/en`, `CAPTIONS/hi` | Subtitles (SRT and WebVTT), timed to the recordings |
| `PLAYER/index.html` | A page that plays every module, with a working English / हिंदी switch |
| `RENDERED/en`, `RENDERED/hi` | The videos (MP4, 1920×1080, H.264 and AAC, subtitles inside). Not in git: made locally |
| `RECORDINGS/` | The raw screen recordings downloaded from GitHub Actions. Not in git |
| `AUDIO/` | The narration clips. Not in git |
| `tools/build.py`, `tools/serve.py` | The pipeline, and a local server for the player |

## Watching

```bash
python3 docs/training/tools/serve.py
```

Then open http://127.0.0.1:8765/PLAYER/ and choose the language at the top. The video, its subtitles
and the page switch together, and the video keeps its place, because both languages share one
recording. (`serve.py` sends byte ranges, which video seeking needs; Python's plain `http.server`
does not.) The page is also meant to work opened straight from disk, since its subtitles are inlined,
but only the served version has been tested. The MP4s also play in any video player; turn their
subtitles on there.

## Building the videos

Needs a Mac (the voices are macOS's Rishi and Lekha), `uv`, `gh`, and nothing else installed:
`ffmpeg` comes from the `imageio-ffmpeg` package.

```bash
# 1. Narration and how long each beat needs (commit SCRIPTS/durations.json)
uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py narrate

# 2. Record on GitHub Actions (also runs on every push to the scripts or recordings)
gh workflow run training.yml

# 3. Download that run's recordings
gh run download <run-id> -D docs/training/RECORDINGS/run-<run-id>

# 4. Assemble both languages, check them, build the player
uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py assemble docs/training/RECORDINGS/run-<run-id>/training-recordings-<run-id>/training
uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py check
uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py player
```

## Changing a video

1. Edit the narration in `SCRIPTS/mNN-*.json`: each beat has `en` and `hi` text.
2. If a beat's action changes, edit `frontend/training/specs/school.spec.ts`. Each beat's action runs
   while its narration plays, and the recording **checks** what the narration claims, so a video can't
   show something that doesn't happen.
3. Run steps 1–4 again. The modules always record in order, because each continues the school the
   previous one built.

## Rules the series keeps

- Only the real application, on a throwaway copy: never production, never real people's data.
- Only features that work (VERIFIED_FEATURE_MATRIX): nothing that exists only as a plan feature name.
- No prices read out, and nothing presented as official CBSE policy. The 9-band scale is ScoreCode's
  CBSE-style starting template.
- ScoreCode's four roles as they are: no parent, principal or coordinator accounts.
