"""S3 / MinIO object storage client and presigned-URL helpers.

The API never proxies object bytes for delivery: clients PUT uploads and GET
downloads via short-lived presigned URLs. A separate *public* endpoint URL is
used when minting URLs handed to browsers so that internal Docker hostnames
(e.g. ``minio:9000``) are not leaked to clients.
"""

from __future__ import annotations

import json
from functools import lru_cache

import boto3
from botocore.client import Config

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

BUCKETS = (settings.bucket_uploads, settings.bucket_outputs, settings.bucket_exports)


def _client(endpoint_url: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        use_ssl=settings.s3_use_ssl,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@lru_cache
def _internal_client():
    return _client(settings.s3_endpoint_url)


@lru_cache
def _public_client():
    return _client(settings.s3_public_endpoint_url)


def ensure_buckets() -> None:
    """Create the configured buckets if they don't yet exist (idempotent)."""

    c = _internal_client()
    existing = {b["Name"] for b in c.list_buckets().get("Buckets", [])}
    for bucket in BUCKETS:
        if bucket not in existing:
            c.create_bucket(Bucket=bucket)
            logger.info("bucket_created", bucket=bucket)


def apply_lifecycle_policies() -> None:
    """Apply retention/lifecycle rules.

    - ``exports`` are user data archives: expire after 7 days.
    - ``uploads``/``outputs`` rely on application-driven purge but get a long
      backstop expiry to bound storage growth from abandoned objects.
    """

    c = _internal_client()
    rules = {
        settings.bucket_exports: 7,
        settings.bucket_uploads: 365,
        settings.bucket_outputs: 365,
    }
    for bucket, days in rules.items():
        c.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": f"{bucket}-expiry",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Expiration": {"Days": days},
                    }
                ]
            },
        )
    logger.info("lifecycle_applied")


def set_public_read(bucket: str) -> None:
    """Allow anonymous GET on a bucket (used for the CDN-fronted outputs edge)."""

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }
    _internal_client().put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))


def presign_put(bucket: str, key: str, content_type: str, ttl: int | None = None) -> str:
    return _public_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=ttl or settings.presign_ttl_seconds,
    )


def presign_get(bucket: str, key: str, ttl: int | None = None) -> str:
    return _public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl or settings.presign_ttl_seconds,
    )


def put_object(bucket: str, key: str, data: bytes, content_type: str) -> None:
    _internal_client().put_object(
        Bucket=bucket, Key=key, Body=data, ContentType=content_type
    )


def get_object(bucket: str, key: str) -> bytes:
    return _internal_client().get_object(Bucket=bucket, Key=key)["Body"].read()


def object_exists(bucket: str, key: str) -> bool:
    try:
        _internal_client().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # noqa: BLE001
        return False


def delete_object(bucket: str, key: str) -> None:
    _internal_client().delete_object(Bucket=bucket, Key=key)


def health_check() -> bool:
    try:
        _internal_client().list_buckets()
        return True
    except Exception:  # noqa: BLE001
        return False
