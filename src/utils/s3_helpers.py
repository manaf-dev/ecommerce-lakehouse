"""Thin boto3 helpers for S3 list / copy / delete operations."""

from __future__ import annotations

from typing import Any


def list_s3_objects(client: Any, bucket: str, prefix: str) -> list[str]:
    """Return all object keys under *bucket/prefix* (paginates automatically).

    Args:
        client: A boto3 S3 client.
        bucket: Bucket name.
        prefix: Key prefix to list (e.g. "raw/products/").

    Returns:
        List of object key strings.
    """
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def copy_s3_object(
    client: Any,
    source_bucket: str,
    source_key: str,
    dest_bucket: str,
    dest_key: str,
) -> None:
    """Copy a single S3 object from source to destination.

    Args:
        client: A boto3 S3 client.
        source_bucket: Source bucket name.
        source_key: Source object key.
        dest_bucket: Destination bucket name.
        dest_key: Destination object key.
    """
    client.copy_object(
        CopySource={"Bucket": source_bucket, "Key": source_key},
        Bucket=dest_bucket,
        Key=dest_key,
    )


def delete_s3_object(client: Any, bucket: str, key: str) -> None:
    """Delete a single S3 object.

    Args:
        client: A boto3 S3 client.
        bucket: Bucket name.
        key: Object key to delete.
    """
    client.delete_object(Bucket=bucket, Key=key)
