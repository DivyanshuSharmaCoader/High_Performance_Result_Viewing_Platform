"""Two-tier cache: in-process TTL LRU in front of optional Redis (docs/11 §2.5).

Redis is never a source of truth. Any Redis error opens a circuit breaker for a short cool-down so
requests don't wait on Redis timeouts; during that time the local tier alone is used. Tenant keys
must be built with ``TenantContext.cache_key`` (isolation layer L5).
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Any, Protocol

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.metrics import CACHE_EVENTS

log = get_logger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_s: int) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def incr(self, key: str, ttl_s: int) -> int: ...


class LocalCache:
    """Bounded in-process TTL cache (per worker process)."""

    def __init__(self, max_entries: int = 10_000) -> None:
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_entries

    async def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl_s: int) -> None:
        self._data[key] = (time.monotonic() + ttl_s, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._data.pop(k, None)

    async def incr(self, key: str, ttl_s: int) -> int:
        current = await self.get(key)
        value = int(current or 0) + 1
        if current is None:
            await self.set(key, value, ttl_s)
        else:
            expires, _ = self._data[key]
            self._data[key] = (expires, value)
        return value

    def clear(self) -> None:
        self._data.clear()


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_s: float = 10.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._failures = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        return time.monotonic() < self._open_until

    @property
    def state(self) -> str:
        return "open" if self.is_open else "closed"

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open_until = time.monotonic() + self.cooldown_s
            self._failures = 0


class TieredCache:
    """Local tier always; Redis tier when configured and healthy."""

    def __init__(
        self,
        redis_client: aioredis.Redis | None,
        local: LocalCache | None = None,
        local_ttl_s: int = 30,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.redis = redis_client
        self.local = local or LocalCache()
        self.local_ttl_s = local_ttl_s
        self.breaker = breaker or CircuitBreaker()

    @property
    def redis_available(self) -> bool:
        return self.redis is not None and not self.breaker.is_open

    async def _redis_call(self, op: str, coro: Any) -> Any:
        try:
            result = await coro
        except (RedisError, OSError, TimeoutError) as exc:
            self.breaker.record_failure()
            CACHE_EVENTS.labels(cache="redis", event="error").inc()
            log.warning("redis_unavailable", op=op, error_code=type(exc).__name__)
            return _MISS
        self.breaker.record_success()
        return result

    async def get(self, key: str, *, local_ttl_s: int | None = None) -> Any | None:
        value = await self.local.get(key)
        if value is not None:
            CACHE_EVENTS.labels(cache="local", event="hit").inc()
            return value
        CACHE_EVENTS.labels(cache="local", event="miss").inc()
        if not self.redis_available:
            return None
        assert self.redis is not None
        raw = await self._redis_call("get", self.redis.get(key))
        if raw is _MISS or raw is None:
            CACHE_EVENTS.labels(cache="redis", event="miss").inc()
            return None
        CACHE_EVENTS.labels(cache="redis", event="hit").inc()
        value = json.loads(raw)
        await self.local.set(key, value, local_ttl_s or self.local_ttl_s)
        return value

    async def set(self, key: str, value: Any, ttl_s: int, *, local_ttl_s: int | None = None) -> None:
        await self.local.set(key, value, min(ttl_s, local_ttl_s or self.local_ttl_s))
        if self.redis_available:
            assert self.redis is not None
            await self._redis_call("set", self.redis.set(key, json.dumps(value, default=str), ex=ttl_s))

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        await self.local.delete(*keys)
        if self.redis_available:
            assert self.redis is not None
            await self._redis_call("delete", self.redis.delete(*keys))

    async def incr(self, key: str, ttl_s: int) -> int:
        if self.redis_available:
            assert self.redis is not None
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_s, nx=True)
            result = await self._redis_call("incr", pipe.execute())
            if result is not _MISS:
                return int(result[0])
        return await self.local.incr(key, ttl_s)


class _Miss:
    pass


_MISS = _Miss()


def build_redis(url: str | None, timeout_s: float, connect_timeout_s: float = 1.0) -> aioredis.Redis | None:
    if not url:
        return None
    return aioredis.from_url(
        url,
        socket_timeout=timeout_s,
        socket_connect_timeout=connect_timeout_s,
        health_check_interval=30,
        decode_responses=True,
    )
