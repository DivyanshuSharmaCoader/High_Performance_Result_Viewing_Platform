"""UUIDv7 identifiers generated in the application (decision D7, docs/07 §1).

Layout (RFC 9562 §5.7): 48-bit Unix epoch milliseconds | version 7 | 12 bits | variant | 62 bits.
The 12 ``rand_a`` bits are used as a per-process monotonic counter so that ids generated within the
same millisecond still sort in creation order (RFC 9562 §6.2, method 1).
"""

from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0
_COUNTER_MAX = 0xFFF


def uuid7() -> uuid.UUID:
    global _last_ms, _counter
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms = now_ms
            _counter = int.from_bytes(os.urandom(2), "big") & 0x3FF  # leave headroom for increments
        else:
            # Same millisecond (or clock moved backwards): keep using the last timestamp.
            _counter += 1
            if _counter > _COUNTER_MAX:
                _last_ms += 1
                _counter = 0
        ms = _last_ms
        counter = _counter
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)


def uuid7_timestamp_ms(value: uuid.UUID) -> int:
    return value.int >> 80
