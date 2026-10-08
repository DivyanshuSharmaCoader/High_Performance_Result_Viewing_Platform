"""Requests per 10-second window by status, from the API's JSON request logs on stdin (P14.5).

    docker compose logs --no-log-prefix api | python3 benchmarks/k6/timeline.py [--around EPOCH]

Shows how a failure injected during a run played out: when errors started, what status they had, and when
service recovered. ``--around`` marks the window of the injection.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import UTC, datetime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--around", default="", help="epoch seconds of the injected failure (may be empty)")
    args = parser.parse_args()
    around = float(args.around) if args.around.strip() else None
    windows: dict[int, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    slow: dict[int, int] = collections.Counter()
    for line in sys.stdin:
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") != "request":
            continue
        t = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
        w = int(t // 10 * 10)
        windows[w][int(e["status"])] += 1
        if float(e.get("duration_ms", 0)) > 1000:
            slow[w] += 1
    for w in sorted(windows):
        c = windows[w]
        mark = " <== injected" if around is not None and w <= around < w + 10 else ""
        statuses = " ".join(f"{k}:{v}" for k, v in sorted(c.items()))
        print(f"{datetime.fromtimestamp(w, UTC):%H:%M:%S} total {sum(c.values()):5d}  >1s {slow[w]:4d}  {statuses}{mark}")


if __name__ == "__main__":
    main()
