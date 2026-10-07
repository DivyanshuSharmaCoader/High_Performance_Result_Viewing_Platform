"""Token-bucket rate limiting: atomic Redis Lua script with an in-process fallback (docs/10 §7).

If Redis is unavailable the limiter degrades to per-process buckets — coarser across nodes but still
protective — instead of failing open or failing every request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from redis.exceptions import RedisError

from app.core.cache import TieredCache
from app.core.errors import RateLimited
from app.core.logging import get_logger
from app.core.metrics import RATE_LIMITED

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Bucket:
    name: str
    rate_per_s: float  # sustained refill rate
    burst: int  # bucket capacity

    @classmethod
    def per_minute(cls, name: str, per_minute: float, burst: int | None = None) -> Bucket:
        return cls(name, per_minute / 60.0, burst if burst is not None else max(1, int(per_minute)))

    @classmethod
    def per_hour(cls, name: str, per_hour: float, burst: int | None = None) -> Bucket:
        return cls(name, per_hour / 3600.0, burst if burst is not None else max(1, int(per_hour)))


# Defaults from docs/10 §7 — tune after load tests (docs/11).
# Sign-in per network address. A whole school lab, or thousands of phones behind one mobile carrier's NAT,
# share an address on result day, so *every* attempt only meets a flood ceiling; *failed* attempts have
# their own, much tighter bucket (credential stuffing), and each account its own limit and lockout.
LOGIN_PER_IP = Bucket.per_minute("login_ip", 3000, burst=1000)
LOGIN_FAILURES_PER_IP = Bucket.per_minute("login_fail_ip", 60, burst=60)
LOGIN_PER_ACCOUNT = Bucket.per_minute("login_account", 10, burst=10)
PASSWORD_RESET = Bucket.per_hour("password_reset", 3, burst=3)
ACTIVATION = Bucket.per_hour("activation", 5, burst=5)  # per enrollment no. (docs/10 §7)
# Per network address: generous, because a whole class often activates from one school network (NAT).
# Guessing a 10-character code (32^10 combinations) stays hopeless at this rate.
ACTIVATION_PER_IP = Bucket.per_hour("activation_ip", 120, burst=60)
VERIFY_PER_IP = Bucket.per_minute("verify_ip", 60, burst=30)
API_PER_SESSION = Bucket.per_minute("api_session", 300, burst=100)
IMPORTS_PER_TENANT = Bucket.per_hour("imports_tenant", 30, burst=10)
SIGNUP_PER_IP = Bucket.per_hour("signup_ip", 5, burst=5)
PLATFORM_LOGIN_PER_IP = Bucket.per_minute("platform_login_ip", 10, burst=5)

_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local peek = tonumber(ARGV[4] or '0')
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = burst end
if ts == nil then ts = now end
tokens = math.min(burst, tokens + math.max(0, now - ts) * rate)
local allowed = 0
local retry = 0
if tokens >= cost then
  if peek == 0 then tokens = tokens - cost end
  allowed = 1
else
  retry = (cost - tokens) / rate
end
if peek == 0 then
  redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
  redis.call('EXPIRE', key, math.ceil(burst / rate) + 5)
end
return {allowed, tostring(retry)}
"""


def login_ip_bucket(settings: Any) -> Bucket:
    return Bucket.per_minute(
        LOGIN_PER_IP.name, settings.rate_login_ip_per_minute, burst=settings.rate_login_ip_burst
    )


def login_failure_bucket(settings: Any) -> Bucket:
    return Bucket.per_minute(
        LOGIN_FAILURES_PER_IP.name,
        settings.rate_login_failures_ip_per_minute,
        burst=settings.rate_login_failures_ip_burst,
    )


def activation_ip_bucket(settings: Any) -> Bucket:
    return Bucket.per_hour(
        ACTIVATION_PER_IP.name,
        settings.rate_activation_ip_per_hour,
        burst=max(1, settings.rate_activation_ip_per_hour // 2),
    )


def signup_ip_bucket(settings: Any) -> Bucket:
    return Bucket.per_hour(SIGNUP_PER_IP.name, settings.rate_signup_ip_per_hour)


class RateLimiter:
    def __init__(self, cache: TieredCache) -> None:
        self.cache = cache
        self._local: dict[str, tuple[float, float]] = {}
        self._script: Any = None
        if cache.redis is not None:
            self._script = cache.redis.register_script(_LUA)

    async def hit(self, bucket: Bucket, identity: str, cost: int = 1) -> None:
        """Consume ``cost`` tokens or raise ``RateLimited`` with a Retry-After hint."""
        key = f"rl:{bucket.name}:{identity}"
        allowed, retry_after = await self._take(key, bucket, cost)
        if not allowed:
            RATE_LIMITED.labels(bucket=bucket.name).inc()
            raise RateLimited(retry_after_s=int(retry_after) + 1)

    async def check(self, bucket: Bucket, identity: str, cost: int = 1) -> None:
        """Raise ``RateLimited`` if a ``hit`` would fail now, without consuming anything."""
        key = f"rl:{bucket.name}:{identity}"
        allowed, retry_after = await self._take(key, bucket, cost, peek=True)
        if not allowed:
            RATE_LIMITED.labels(bucket=bucket.name).inc()
            raise RateLimited(retry_after_s=int(retry_after) + 1)

    async def consume(self, bucket: Bucket, identity: str, cost: int = 1) -> bool:
        """Take ``cost`` tokens if there are enough; report whether there were (never raises)."""
        allowed, _ = await self._take(f"rl:{bucket.name}:{identity}", bucket, cost)
        return allowed

    async def _take(self, key: str, bucket: Bucket, cost: int, *, peek: bool = False) -> tuple[bool, float]:
        if self._script is not None and self.cache.redis_available:
            try:
                allowed, retry = await self._script(
                    keys=[key], args=[bucket.rate_per_s, bucket.burst, cost, 1 if peek else 0]
                )
                self.cache.breaker.record_success()
                return bool(int(allowed)), float(retry)
            except (RedisError, OSError, TimeoutError) as exc:
                self.cache.breaker.record_failure()
                log.warning("ratelimit_redis_unavailable", error_code=type(exc).__name__)
        return self._take_local(key, bucket, cost, peek=peek)

    def _local_state(self, key: str, bucket: Bucket) -> tuple[float, float]:
        now = time.monotonic()
        tokens, ts = self._local.get(key, (float(bucket.burst), now))
        tokens = min(float(bucket.burst), tokens + max(0.0, now - ts) * bucket.rate_per_s)
        return tokens, now

    def _take_local(self, key: str, bucket: Bucket, cost: int, *, peek: bool = False) -> tuple[bool, float]:
        tokens, now = self._local_state(key, bucket)
        if peek:
            return (True, 0.0) if tokens >= cost else (False, (cost - tokens) / bucket.rate_per_s)
        if tokens >= cost:
            self._local[key] = (tokens - cost, now)
            self._evict()
            return True, 0.0
        self._local[key] = (tokens, now)
        return False, (cost - tokens) / bucket.rate_per_s

    def _evict(self) -> None:
        if len(self._local) > 50_000:
            # Drop the oldest half; buckets refill anyway, so this only loosens limits briefly.
            for k in list(self._local.keys())[:25_000]:
                self._local.pop(k, None)

    def reset_local(self) -> None:
        self._local.clear()
