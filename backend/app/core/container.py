"""Infrastructure container: the adapters every module may depend on (dependency inversion, docs/08 §3).

Built once per process (API or worker). Tests construct it with alternative settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.cache import LocalCache, TieredCache, build_redis
from app.core.config import Settings
from app.core.db import Database
from app.core.mailer import Mailer, SmtpMailer
from app.core.ratelimit import RateLimiter
from app.core.security import FieldCipher, PasswordService
from app.core.storage import ObjectStore, S3ObjectStore


@dataclass
class Infra:
    settings: Settings
    db: Database
    cache: TieredCache
    limiter: RateLimiter
    storage: ObjectStore
    mailer: Mailer
    passwords: PasswordService
    cipher: FieldCipher

    @classmethod
    def build(cls, settings: Settings, *, app_name: str = "scorecode-api") -> Infra:
        cache = TieredCache(
            build_redis(settings.redis_url, settings.redis_timeout_s),
            LocalCache(),
            local_ttl_s=settings.cache_local_ttl_s,
        )
        return cls(
            settings=settings,
            db=Database(settings, app_name=app_name),
            cache=cache,
            limiter=RateLimiter(cache),
            storage=S3ObjectStore(settings),
            mailer=SmtpMailer(settings),
            passwords=PasswordService(settings),
            cipher=FieldCipher(settings.secret_key.get_secret_value()),
        )

    async def close(self) -> None:
        await self.db.dispose()
        if self.cache.redis is not None:
            await self.cache.redis.aclose()
