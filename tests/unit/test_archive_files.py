"""Unit tests for the archive-files Lambda."""

from __future__ import annotations

from unittest.mock import patch

from lambda_functions.archive_files import handler, run_archive

_BUCKET = "test-lakehouse-bucket"


class TestArchiveFilesHandler:
    def test_handler_delegates_to_run_archive(self):
        with patch(
            "lambda_functions.archive_files.run_archive",
            return_value={"archived": 2, "deleted": 2},
        ) as mock_run:
            event = {"bucket": _BUCKET, "run_id": "run-1"}
            result = handler(event, None)

        mock_run.assert_called_once_with(event)
        assert result == {"archived": 2, "deleted": 2}

    def test_archive_all_datasets(self, s3_client):
        s3_client.create_bucket(Bucket=_BUCKET)
        s3_client.put_object(Bucket=_BUCKET, Key="raw/orders/apr.csv", Body=b"data")

        result = run_archive({"bucket": _BUCKET, "run_id": "run-1"})

        assert result == {"archived": 1, "deleted": 1}
        archived = s3_client.list_objects_v2(Bucket=_BUCKET, Prefix="archived/orders/")
        assert archived["Contents"][0]["Key"] == "archived/orders/run_id=run-1/apr.csv"
        assert "Contents" not in s3_client.list_objects_v2(Bucket=_BUCKET, Prefix="raw/orders/")
