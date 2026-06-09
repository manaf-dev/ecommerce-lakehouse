"""AWS Glue 3.0 Python Shell archive job.

Copies source files from the raw S3 zone to the archive zone, then deletes
the originals.  Copy-then-delete order is strictly enforced: all copies must
succeed before any delete is attempted, so a delete failure leaves data in
both locations (no data loss).

Args (via getResolvedOptions):
  --dataset        Dataset name (products, orders, order_items)
  --raw_prefix     S3 URI to source files  (e.g. s3://bucket/raw/products/)
  --archive_prefix S3 URI for archive dest (e.g. s3://bucket/archive/products/run/)
  --run_id         Step Functions execution name

Entry point for Glue 3.0 runtime: ``main()``.
Entry point for tests: ``run_archive(args)``.
"""

from __future__ import annotations

import sys

import boto3

from utils.logger import get_logger
from utils.s3_helpers import copy_s3_object, delete_s3_object, list_s3_objects


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split ``s3://bucket/prefix`` into ``(bucket, prefix)``."""
    tail = uri[len("s3://") :]
    bucket, _, prefix = tail.partition("/")
    return bucket, prefix


def run_archive(args: dict) -> dict:
    """Core archive logic — callable from tests without a Glue runtime.

    Processing sequence (per contracts/glue-job-interface.md):
      1. List all objects under raw_prefix.
      2. Copy each object to archive_prefix + basename.
      3. After ALL copies succeed: delete each source object.

    Args:
        args: Dict with keys: dataset, raw_prefix, archive_prefix, run_id.

    Returns:
        Counts dict with keys: ``archived``, ``deleted``.
    """
    dataset: str = args["dataset"]
    raw_prefix: str = args["raw_prefix"]
    archive_prefix: str = args["archive_prefix"]
    run_id: str = args.get("run_id", "local-run")

    logger = get_logger("archive_files", dataset=dataset, run_id=run_id)

    src_bucket, src_prefix = _parse_s3_uri(raw_prefix)
    dst_bucket, dst_prefix = _parse_s3_uri(archive_prefix)
    # Normalise prefix (no trailing slash duplication)
    dst_prefix = dst_prefix.rstrip("/")

    client = boto3.client("s3")
    keys = list_s3_objects(client, src_bucket, src_prefix)

    logger.info(f"Archiving {len(keys)} files from {raw_prefix} to {archive_prefix}")

    if not keys:
        logger.info("Archived 0 files. Deleted 0 source objects.")
        return {"archived": 0, "deleted": 0}

    # ── Phase 1: copy ALL files ──────────────────────────────────────────────
    for key in keys:
        filename = key.rsplit("/", 1)[-1]
        dest_key = f"{dst_prefix}/{filename}"
        copy_s3_object(client, src_bucket, key, dst_bucket, dest_key)

    # ── Phase 2: delete source files (only after all copies succeed) ─────────
    for key in keys:
        delete_s3_object(client, src_bucket, key)

    count = len(keys)
    logger.info(f"Archived {count} files. Deleted {count} source objects.")
    return {"archived": count, "deleted": count}


def main() -> None:
    """AWS Glue 3.0 Python Shell entry point."""
    try:
        from awsglue.utils import getResolvedOptions  # noqa: PLC0415

        params = getResolvedOptions(sys.argv, ["dataset", "raw_prefix", "archive_prefix", "run_id"])
    except ImportError:
        import argparse  # noqa: PLC0415

        parser = argparse.ArgumentParser(description="Local archive_files runner")
        for flag in ["--dataset", "--raw_prefix", "--archive_prefix", "--run_id"]:
            parser.add_argument(flag)
        ns = parser.parse_args()
        params = {k: v for k, v in vars(ns).items() if v is not None}

    run_archive(params)


if __name__ == "__main__":
    main()
