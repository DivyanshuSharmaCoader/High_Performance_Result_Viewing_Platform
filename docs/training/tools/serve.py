#!/usr/bin/env python3
"""Serve docs/training on http://127.0.0.1:8765 with byte ranges, so the player's videos can seek.

    python3 docs/training/tools/serve.py        then open http://127.0.0.1:8765/PLAYER/

Python's own `http.server` sends whole files only; browsers then refuse to seek in a video (and the
player's language switch can't keep its place). Opening PLAYER/index.html straight from disk works
too.
"""

from __future__ import annotations

import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):  # type: ignore[override]
        self._left = None
        rng = self.headers.get("Range")
        path = Path(self.translate_path(self.path))
        if not rng or not path.is_file():
            return super().send_head()
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
        size = path.stat().st_size
        if not m or (not m[1] and not m[2]):
            self.send_error(416)
            return None
        start, end = (
            (int(m[1]), int(m[2] or size - 1))
            if m[1]
            else (max(0, size - int(m[2])), size - 1)
        )
        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        end = min(end, size - 1)
        f = path.open("rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._left = end - start + 1
        return f

    def copyfile(self, source, outputfile):  # type: ignore[override]
        left = self._left
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(65536, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)
        return None

    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(
        ("127.0.0.1", port), partial(RangeHandler, directory=str(ROOT))
    )
    print(f"http://127.0.0.1:{port}/PLAYER/")
    server.serve_forever()
