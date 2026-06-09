"""Unit tests for src/utils/s3_helpers.py — all AWS calls mocked via moto."""

import pytest
from moto import mock_aws

from utils.s3_helpers import copy_s3_object, delete_s3_object, list_s3_objects

BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture
def s3(aws_credentials):
    import boto3

    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        yield client


def _put(client, key: str, body: str = "data") -> None:
    client.put_object(Bucket=BUCKET, Key=key, Body=body.encode())


class TestListS3Objects:
    def test_empty_prefix_returns_empty_list(self, s3):
        result = list_s3_objects(s3, BUCKET, "raw/products/")
        assert result == []

    def test_single_object_returned(self, s3):
        _put(s3, "raw/products/file.csv")
        result = list_s3_objects(s3, BUCKET, "raw/products/")
        assert result == ["raw/products/file.csv"]

    def test_multiple_objects_returned(self, s3):
        _put(s3, "raw/orders/jan.xlsx")
        _put(s3, "raw/orders/feb.xlsx")
        result = list_s3_objects(s3, BUCKET, "raw/orders/")
        assert sorted(result) == ["raw/orders/feb.xlsx", "raw/orders/jan.xlsx"]

    def test_prefix_filter_excludes_other_keys(self, s3):
        _put(s3, "raw/products/p.csv")
        _put(s3, "raw/orders/o.xlsx")
        result = list_s3_objects(s3, BUCKET, "raw/products/")
        assert result == ["raw/products/p.csv"]

    def test_returns_all_keys_across_pages(self, s3):
        keys = [f"raw/items/file_{i}.csv" for i in range(5)]
        for k in keys:
            _put(s3, k)
        result = list_s3_objects(s3, BUCKET, "raw/items/")
        assert sorted(result) == sorted(keys)


class TestCopyS3Object:
    def test_copy_creates_object_at_dest(self, s3):
        _put(s3, "raw/products/src.csv", body="content")
        copy_s3_object(s3, BUCKET, "raw/products/src.csv", BUCKET, "archive/products/src.csv")
        body = s3.get_object(Bucket=BUCKET, Key="archive/products/src.csv")["Body"].read()
        assert body == b"content"

    def test_source_object_still_exists_after_copy(self, s3):
        _put(s3, "raw/products/keep.csv")
        copy_s3_object(s3, BUCKET, "raw/products/keep.csv", BUCKET, "archive/products/keep.csv")
        resp = s3.head_object(Bucket=BUCKET, Key="raw/products/keep.csv")
        assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200


class TestDeleteS3Object:
    def test_delete_removes_object(self, s3):
        _put(s3, "raw/products/del.csv")
        delete_s3_object(s3, BUCKET, "raw/products/del.csv")
        result = list_s3_objects(s3, BUCKET, "raw/products/")
        assert "raw/products/del.csv" not in result

    def test_delete_only_removes_target_key(self, s3):
        _put(s3, "raw/products/a.csv")
        _put(s3, "raw/products/b.csv")
        delete_s3_object(s3, BUCKET, "raw/products/a.csv")
        remaining = list_s3_objects(s3, BUCKET, "raw/products/")
        assert remaining == ["raw/products/b.csv"]
