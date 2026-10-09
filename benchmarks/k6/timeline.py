"""From the API's JSON request logs on stdin (P14.5, NFR-3).

    docker compose logs --no-log-prefix api | python3 benchmarks/k6/timeline.py [--around EPOCH]
    docker compose logs --no-log-prefix --since 2026-10-09T10:00:00Z api | python3 benchmarks/k6/timeline.py --latency

Default: requests per 10-second window by status, showing how an injected failure played out (when errors
started, what status they had, when service recovered). ``--around`` marks the injection's window.

``--latency``: server-side duration percentiles per endpoint (the API's own measure, from the moment the
request reaches it to the response; no proxy, network or load-generator queueing). NFR-3 is stated this
way.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from datetime import UTC, datetime

_ID = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def latency(lines: list[str]) -> None:
    durations: dict[str, list[float]] = collections.defaultdict(list)
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "request" and int(e.get("status", 0)) == 200 and "duration_ms" in e:
            durations[_ID.sub("/{id}", e.get("path", "?"))].append(float(e["duration_ms"]))
    for path, values in sorted(durations.items(), key=lambda kv: -len(kv[1])):
        if len(values) < 20:
            continue
        q = statistics.quantiles(values, n=100)
        print(f"{path:45s} n={len(values):7d} p50={q[49]:8.1f}ms p95={q[94]:8.1f}ms p99={q[98]:8.1f}ms")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--around", default="", help="epoch seconds of the injected failure (may be empty)")
    parser.add_argument("--latency", action="store_true", help="server-side percentiles per endpoint instead")
    args = parser.parse_args()
    if args.latency:
        latency(sys.stdin.readlines())
        return
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
