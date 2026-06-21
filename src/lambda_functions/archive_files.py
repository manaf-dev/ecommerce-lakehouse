"""Lambda handler — archive raw files to archived/ after successful ingest."""

from __future__ import annotations

import logging
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DATASETS = ("products", "orders", "order_items")


def _list_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def run_archive(args: dict) -> dict:
    """Copy all raw dataset files to archived/, then delete sources."""
    bucket: str = args["bucket"]
    run_id: str = args.get("run_id", "local-run")
    client = boto3.client("s3")

    total_archived = 0

    for dataset in _DATASETS:
        src_prefix = f"raw/{dataset}/"
        dst_prefix = f"archived/{dataset}/run_id={run_id}/"

        keys = _list_keys(client, bucket, src_prefix)
        if not keys:
            logger.info("No files to archive for %s", dataset)
            continue

        for key in keys:
            filename = key.rsplit("/", 1)[-1]
            dest_key = f"{dst_prefix}{filename}"
            client.copy_object(
                Bucket=bucket,
                Key=dest_key,
                CopySource={"Bucket": bucket, "Key": key},
            )

        for key in keys:
            client.delete_object(Bucket=bucket, Key=key)

        logger.info("Archived %s %s files", len(keys), dataset)
        total_archived += len(keys)

    return {"archived": total_archived, "deleted": total_archived}


def handler(event: dict[str, Any], _context: Any) -> dict:
    return run_archive(event)
