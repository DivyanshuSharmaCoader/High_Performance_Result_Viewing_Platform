"""Typed application configuration (12-factor; docs/08 §8).

Every setting comes from the environment (prefix ``SCORECODE_``). The app refuses to start in
production with development defaults for secrets.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105 - explicit dev default, rejected in prod


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCORECODE_", env_file=".env", extra="ignore")

    env: Environment = Environment.DEVELOPMENT
    service_name: str = "scorecode"
    log_level: str = "INFO"
    log_json: bool = True

    # --- Hosts (docs/06 §4). No domain is hard-coded anywhere else. -----------------------------
    base_domain: str = "localhost"
    platform_subdomain: str = "admin"
    verify_subdomain: str = "verify"
    # Port the browser uses (only for building absolute links in emails/QR codes in dev).
    public_port: int | None = 8080
    public_scheme: str = "http"

    # --- Database: three roles (docs/06 §2) -------------------------------------------------------
    database_url_app: str = "postgresql+asyncpg://scorecode_app:app-dev-pw@localhost:55432/scorecode"
    database_url_platform: str = (
        "postgresql+asyncpg://scorecode_platform:platform-dev-pw@localhost:55432/scorecode"
    )
    database_url_migrator: str = (
        "postgresql+asyncpg://scorecode_migrator:migrator-dev-pw@localhost:55432/scorecode"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_s: float = 5.0
    db_statement_cache_size: int = 0  # 0 keeps asyncpg compatible with PgBouncer transaction pooling

    # --- Redis (optional, degradable; docs/11 §2.5) ----------------------------------------------
    redis_url: str | None = None
    redis_timeout_s: float = 0.5  # per operation; the circuit breaker stops repeated waits
    redis_connect_timeout_s: float = 1.0
    cache_local_ttl_s: int = 30

    # --- Object storage (S3 API) ------------------------------------------------------------------
    s3_endpoint_url: str | None = "http://localhost:59000"
    s3_public_endpoint_url: str | None = None  # endpoint browsers use for signed URLs
    s3_region: str = "ap-south-1"
    s3_bucket: str = "scorecode-dev"
    s3_access_key: str = "scorecode"
    s3_secret_key: SecretStr = SecretStr("scorecode-dev-secret")
    signed_url_ttl_s: int = 300

    # --- Email ------------------------------------------------------------------------------------
    smtp_host: str = "localhost"
    smtp_port: int = 51025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    mail_from: str = "ScoreCode <no-reply@scorecode.localhost>"

    # --- Security ---------------------------------------------------------------------------------
    trust_proxy_headers: bool = False  # true only behind our own proxy (Caddy), which sets X-Forwarded-For
    secret_key: SecretStr = SecretStr(DEV_SECRET)
    cookie_secure: bool = False  # True in staging/prod → __Host- prefixed cookies
    argon2_time_cost: int = 2
    argon2_memory_kib: int = 19_456  # OWASP 2023 baseline for Argon2id (m=19 MiB, t=2, p=1)
    argon2_parallelism: int = 1
    argon2_max_concurrency: int = 4  # bounded per process (docs/11 §3)
    student_session_days: int = 30
    staff_session_idle_hours: int = 12
    staff_session_absolute_days: int = 7
    platform_session_hours: int = 8
    # Abuse limits (docs/10 §7). Production defaults; local stacks may relax them for automated tests.
    rate_login_ip_per_minute: int = 20
    rate_login_ip_burst: int = 10
    rate_signup_ip_per_hour: int = 5
    api_session_per_minute: int = 300  # authenticated API calls per session (docs/10 §7)
    api_session_burst: int = 100
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    reauth_window_minutes: int = 10

    # --- Limits -----------------------------------------------------------------------------------
    max_upload_bytes: int = 10 * 1024 * 1024
    max_logo_bytes: int = 1 * 1024 * 1024
    max_import_rows: int = 50_000
    max_import_columns: int = 200
    max_xlsx_uncompressed_bytes: int = 100 * 1024 * 1024

    # --- Jobs -------------------------------------------------------------------------------------
    worker_queues: str = "imports,processing,pdf,publishing,notifications,maintenance"
    worker_concurrency: int = 4
    worker_poll_interval_s: float = 1.0
    job_lease_s: int = 120
    job_max_attempts: int = 5
    jobs_inline: bool = False  # tests may run jobs synchronously after commit

    # --- Observability ----------------------------------------------------------------------------
    sentry_dsn: SecretStr | None = None
    metrics_enabled: bool = True
    expose_docs: bool = True

    # --- Platform bootstrap -----------------------------------------------------------------------
    totp_issuer: str = "ScoreCode"

    session_cache_ttl_s: Annotated[int, Field(ge=0, le=300)] = 60

    @model_validator(mode="after")
    def _production_safety(self) -> Self:
        if self.env in (Environment.STAGING, Environment.PRODUCTION):
            problems: list[str] = []
            if (
                self.secret_key.get_secret_value() == DEV_SECRET
                or len(self.secret_key.get_secret_value()) < 32
            ):
                problems.append("SCORECODE_SECRET_KEY must be set to a random value of >= 32 chars")
            if not self.cookie_secure:
                problems.append("SCORECODE_COOKIE_SECURE must be true outside development")
            if self.public_scheme != "https":
                problems.append("SCORECODE_PUBLIC_SCHEME must be https outside development")
            if self.s3_secret_key.get_secret_value() == "scorecode-dev-secret":
                problems.append("SCORECODE_S3_SECRET_KEY must not use the development default")
            for name in ("database_url_app", "database_url_platform", "database_url_migrator"):
                if "-dev-pw@" in getattr(self, name):
                    problems.append(f"SCORECODE_{name.upper()} uses a development password")
            if problems:
                raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        if len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("SCORECODE_SECRET_KEY must be at least 32 characters")
        return self

    # --- Derived helpers --------------------------------------------------------------------------
    @property
    def is_production_like(self) -> bool:
        return self.env in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def platform_host(self) -> str:
        return f"{self.platform_subdomain}.{self.base_domain}"

    @property
    def verify_host(self) -> str:
        return f"{self.verify_subdomain}.{self.base_domain}"

    def public_origin(self, host: str) -> str:
        port = "" if self.public_port in (None, 80, 443) else f":{self.public_port}"
        return f"{self.public_scheme}://{host}{port}"

    def tenant_origin(self, slug: str) -> str:
        return self.public_origin(f"{slug}.{self.base_domain}")

    @property
    def session_cookie_name(self) -> str:
        return "__Host-sc_session" if self.cookie_secure else "sc_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-sc_csrf" if self.cookie_secure else "sc_csrf"

    @property
    def queues(self) -> list[str]:
        return [q.strip() for q in self.worker_queues.split(",") if q.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
