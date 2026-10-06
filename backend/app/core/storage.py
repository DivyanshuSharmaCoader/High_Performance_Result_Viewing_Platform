"""Object storage over the S3 API (MinIO in dev, S3/R2 in production; docs/05, docs/10 §6).

Keys are always ``tenants/{tenant_id}/{kind}/{uuid}`` — never user-supplied names (L5). Downloads use
short-lived presigned URLs issued only after an authorization check; buckets are private.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

import anyio
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.core.errors import ServiceUnavailable
from app.core.ids import uuid7


def tenant_object_key(tenant_id: uuid.UUID, kind: str, suffix: str = "") -> str:
    if not kind.isidentifier():
        raise ValueError("invalid object kind")
    return f"tenants/{tenant_id}/{kind}/{uuid7()}{suffix}"


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    def presigned_get(self, key: str, *, filename: str | None = None, ttl_s: int | None = None) -> str: ...
    async def ping(self) -> bool: ...


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.ttl_s = settings.signed_url_ttl_s
        common: dict[str, Any] = {
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key.get_secret_value(),
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2, "mode": "standard"},
                connect_timeout=3,
                read_timeout=15,
            ),
        }
        self._client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url, **common)
        self._public = boto3.client(
            "s3", endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url, **common
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await anyio.to_thread.run_sync(
                lambda: self._client.put_object(
                    Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailable("File storage is temporarily unavailable. Try again shortly.") from exc

    async def get(self, key: str) -> bytes:
        try:
            obj = await anyio.to_thread.run_sync(lambda: self._client.get_object(Bucket=self.bucket, Key=key))
            body: bytes = await anyio.to_thread.run_sync(obj["Body"].read)
            return body
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailable("File storage is temporarily unavailable. Try again shortly.") from exc

    async def delete(self, key: str) -> None:
        await anyio.to_thread.run_sync(lambda: self._client.delete_object(Bucket=self.bucket, Key=key))

    def presigned_get(self, key: str, *, filename: str | None = None, ttl_s: int | None = None) -> str:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if filename:
            safe = "".join(c for c in filename if c.isalnum() or c in "-_.")[:120] or "download"
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
        url: str = self._public.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl_s or self.ttl_s
        )
        return url

    async def ping(self) -> bool:
        try:
            await anyio.to_thread.run_sync(lambda: self._client.head_bucket(Bucket=self.bucket))
        except (BotoCoreError, ClientError):
            return False
        return True

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError:
                self._client.create_bucket(Bucket=self.bucket)

        await anyio.to_thread.run_sync(_ensure)
