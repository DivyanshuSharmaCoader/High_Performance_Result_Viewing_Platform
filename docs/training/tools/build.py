#!/usr/bin/env python3
"""Training video pipeline (docs/training/README.md).

    uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py narrate
    uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py assemble RECORDINGS_DIR
    uv run --no-project --with imageio-ffmpeg python docs/training/tools/build.py check

narrate   macOS `say` (Rishi: Indian English; Lekha: Hindi) writes AUDIO/<lang>/<module>/<beat>.m4a and
          SCRIPTS/durations.json, the time each beat needs (the longer language, plus a pause). The
          recorder waits that long, so one recording carries both languages.
assemble  For each recording (<module>.webm + <module>.timeline.json from the training workflow): places
          each beat's narration at the moment the recorder started that beat, writes subtitles (SRT and
          VTT) from the same times, and renders RENDERED/<lang>/<module>.mp4 (H.264, AAC, soft subtitles).
check     Reads every rendered file back: duration, resolution, audio and subtitle streams, loudness, and
          that no narration runs past the end.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # docs/training
SCRIPTS, AUDIO, CAPTIONS, RENDERED = ROOT / "SCRIPTS", ROOT / "AUDIO", ROOT / "CAPTIONS", ROOT / "RENDERED"
VOICES = {"en": ("Rishi", 165), "hi": ("Lekha", 160)}
PAUSE_MS = 700  # silence after each beat before the next starts


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def modules() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(SCRIPTS.glob("m*.json"))]


def duration_ms(path: Path) -> int:
    out = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, check=True).stdout
    return int(float(re.search(r"estimated duration: ([\d.]+)", out)[1]) * 1000)


def narrate() -> None:
    durations: dict[str, dict[str, int]] = {}
    for m in modules():
        durations[m["id"]] = {}
        for beat in m["beats"]:
            longest = 0
            for lang, (voice, rate) in VOICES.items():
                out = AUDIO / lang / m["id"] / f"{beat['id']}.m4a"
                out.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["say", "-v", voice, "-r", str(rate), "--file-format=m4af", "--data-format=aac", "-o", str(out),
                     beat[lang]],
                    check=True,
                )  # fmt: skip
                longest = max(longest, duration_ms(out))
            durations[m["id"]][beat["id"]] = longest + PAUSE_MS
        total = sum(durations[m["id"]].values()) / 1000
        print(f"{m['id']}: {len(m['beats'])} beats, narration needs {total:.0f} s")
    (SCRIPTS / "durations.json").write_text(json.dumps(durations, indent=1) + "\n")


def stamp(ms: int, sep: str) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def assemble(recordings: Path) -> None:
    for m in modules():
        video = recordings / f"{m['id']}.webm"
        timeline_file = recordings / f"{m['id']}.timeline.json"
        if not video.exists() or not timeline_file.exists():
            print(f"{m['id']}: no recording yet, skipped")
            continue
        timeline = json.loads(timeline_file.read_text())  # [{"id": beat, "at": ms from video start}]
        starts = {t["id"]: t["at"] for t in timeline}
        missing = [b["id"] for b in m["beats"] if b["id"] not in starts]
        if missing:
            sys.exit(f"{m['id']}: the recording has no start time for beats {missing}")
        for lang in VOICES:
            clips = [(starts[b["id"]], AUDIO / lang / m["id"] / f"{b['id']}.m4a", b[lang]) for b in m["beats"]]
            # Subtitles: each beat from its start until its narration ends.
            CAPTIONS.joinpath(lang).mkdir(parents=True, exist_ok=True)
            srt, vtt = [], ["WEBVTT", ""]
            for n, (at, path, text) in enumerate(clips, 1):
                end = at + duration_ms(path)
                srt += [str(n), f"{stamp(at, ',')} --> {stamp(end, ',')}", text, ""]
                vtt += [f"{stamp(at, '.')} --> {stamp(end, '.')}", text, ""]
            srt_path = CAPTIONS / lang / f"{m['id']}.srt"
            srt_path.write_text("\n".join(srt))
            (CAPTIONS / lang / f"{m['id']}.vtt").write_text("\n".join(vtt))
            # Audio: every clip delayed to its start, mixed (they never overlap), loudness normalised.
            args = [ffmpeg(), "-y", "-loglevel", "error", "-i", str(video)]
            for _, path, _ in clips:
                args += ["-i", str(path)]
            delays = "".join(f"[{i + 1}:a]adelay={at}|{at},aresample=48000[a{i}];" for i, (at, _, _) in enumerate(clips))
            mix = "".join(f"[a{i}]" for i in range(len(clips)))
            filt = f"{delays}{mix}amix=inputs={len(clips)}:normalize=0,loudnorm=I=-16:TP=-1.5[aout]"
            out = RENDERED / lang / f"{m['id']}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            # The window is recorded at 1440×810 and scaled to 1080p, so text stays large on a phone.
            filt = f"[0:v]scale=1920:1080:flags=lanczos,format=yuv420p[vout];{filt}"
            args += ["-i", str(srt_path), "-filter_complex", filt, "-map", "[vout]", "-map", "[aout]",
                     "-map", f"{len(clips) + 1}:s",
                     "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "25",
                     "-c:a", "aac", "-b:a", "128k", "-c:s", "mov_text",
                     "-metadata", f"title={m['title'][lang]}",
                     "-metadata:s:a:0", f"language={'hin' if lang == 'hi' else 'eng'}",
                     "-metadata:s:s:0", f"language={'hin' if lang == 'hi' else 'eng'}",
                     "-movflags", "+faststart", str(out)]  # fmt: skip
            subprocess.run(args, check=True)
            print(f"{m['id']} [{lang}] → {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


def probe(path: Path) -> dict:
    """What ffmpeg says about a file (ffprobe isn't bundled): streams, duration, loudness."""
    info = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    vol = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(path), "-map", "0:a", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr  # fmt: skip
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    return {
        "seconds": int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else 0,
        "video": re.search(r"Video: (\w+).*?(\d{3,4}x\d{3,4})", info),
        "audio": "Audio: aac" in info,
        "subtitles": "Subtitle: mov_text" in info,
        "mean_db": float(m[1]) if (m := re.search(r"mean_volume: (-?[\d.]+) dB", vol)) else None,
        "max_db": float(m[1]) if (m := re.search(r"max_volume: (-?[\d.]+) dB", vol)) else None,
    }


def check() -> None:
    ok = True
    for path in sorted(RENDERED.glob("*/*.mp4")):
        p = probe(path)
        v = p["video"]
        problems = []
        if not v:
            problems.append("no video stream")
        if not p["audio"]:
            problems.append("no audio")
        if not p["subtitles"]:
            problems.append("no subtitles")
        if p["max_db"] is not None and p["max_db"] > -0.5:
            problems.append(f"clipping risk (max {p['max_db']} dB)")
        if p["mean_db"] is not None and p["mean_db"] < -40:
            problems.append(f"very quiet (mean {p['mean_db']} dB)")
        srt = CAPTIONS / path.parent.name / f"{path.stem}.srt"
        last_end = max((int(h) * 3600 + int(mi) * 60 + int(s) for h, mi, s in re.findall(r"--> (\d+):(\d+):(\d+)", srt.read_text())), default=0) if srt.exists() else 0
        if last_end > p["seconds"] + 1:
            problems.append(f"narration runs past the end ({last_end}s > {p['seconds']:.0f}s)")
        ok &= not problems
        print(f"{'ok  ' if not problems else 'FAIL'} {path.relative_to(ROOT)}: {p['seconds']:.0f}s, "
              f"{v[1] + ' ' + v[2] if v else '-'}, mean {p['mean_db']} dB, max {p['max_db']} dB"
              + (f"  ← {'; '.join(problems)}" if problems else ""))  # fmt: skip
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "narrate":
        if not shutil.which("say"):
            sys.exit("narrate needs macOS `say` (voices Rishi and Lekha)")
        narrate()
    elif cmd == "assemble" and len(sys.argv) == 3:
        assemble(Path(sys.argv[2]))
    elif cmd == "check":
        check()
    else:
        sys.exit(__doc__)
