"""Integration tests for archive_files Lambda."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lambda_functions.archive_files import run_archive

_BUCKET = "test-lakehouse-bucket"
_BASE_ARGS = {
    "bucket": _BUCKET,
    "run_id": "test",
}


def _create_bucket(s3_client) -> None:
    s3_client.create_bucket(Bucket=_BUCKET)


def _put_objects(s3_client, keys_bodies: dict) -> None:
    for key, body in keys_bodies.items():
        s3_client.put_object(Bucket=_BUCKET, Key=key, Body=body)


def _list_keys(s3_client, prefix: str) -> list[str]:
    resp = s3_client.list_objects_v2(Bucket=_BUCKET, Prefix=prefix)
    return [obj["Key"] for obj in resp.get("Contents", [])]


class TestArchiveFiles:
    def test_archive_copies_and_deletes(self, s3_client):
        _create_bucket(s3_client)
        source_objects = {
            "raw/products/file1.csv": b"row1",
            "raw/products/file2.csv": b"row2",
            "raw/products/file3.csv": b"row3",
        }
        _put_objects(s3_client, source_objects)

        result = run_archive(_BASE_ARGS)

        assert result == {"archived": 3, "deleted": 3}

        for i in range(1, 4):
            body = s3_client.get_object(
                Bucket=_BUCKET,
                Key=f"archived/products/run_id=test/file{i}.csv",
            )["Body"].read()
            assert body == f"row{i}".encode()

        assert _list_keys(s3_client, "raw/products/") == []

    def test_empty_prefix_exits_cleanly(self, s3_client):
        _create_bucket(s3_client)

        result = run_archive(_BASE_ARGS)

        assert result == {"archived": 0, "deleted": 0}
        assert _list_keys(s3_client, "archived/") == []

    def test_copy_before_delete_semantics(self, s3_client):
        _create_bucket(s3_client)
        _put_objects(s3_client, {"raw/products/important.csv": b"critical-data"})

        with patch("lambda_functions.archive_files.boto3.client", return_value=s3_client):
            with patch.object(
                s3_client,
                "delete_object",
                side_effect=RuntimeError("S3 delete deliberately failed"),
            ):
                with pytest.raises(RuntimeError, match="S3 delete deliberately failed"):
                    run_archive(_BASE_ARGS)

        archive_body = s3_client.get_object(
            Bucket=_BUCKET,
            Key="archived/products/run_id=test/important.csv",
        )["Body"].read()
        assert archive_body == b"critical-data"

        raw_body = s3_client.get_object(
            Bucket=_BUCKET,
            Key="raw/products/important.csv",
        )["Body"].read()
        assert raw_body == b"critical-data"
