"""The private reports bucket (Linode Object Storage, S3 API), through boto3 in a worker thread.
Only consented report audio is ever put here (app/reports/), and it's deleted on review."""

import asyncio
from typing import Any, Protocol

import boto3

from app.config import Settings


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def signed_url(self, key: str, seconds: int) -> str: ...


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.reports_bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.reports_endpoint,
            region_name=settings.reports_region,
            aws_access_key_id=settings.reports_access_key,
            aws_secret_access_key=settings.reports_secret_key,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ACL="private",
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def signed_url(self, key: str, seconds: int) -> str:
        """A link that plays the object for `seconds` (the admin page's audio player)."""
        url: str = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=seconds,
        )
        return url


def object_store_for(settings: Settings) -> ObjectStore | None:
    """The reports bucket, or None when it isn't configured (reports then answer 503)."""
    return S3ObjectStore(settings) if settings.reports_configured else None
