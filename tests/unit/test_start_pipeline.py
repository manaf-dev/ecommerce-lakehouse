"""Unit tests for the pipeline starter Lambda."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from lambda_functions.start_pipeline import _derive_order_month, handler

_STATE_MACHINE_ARN = "arn:aws:states:us-east-1:123:stateMachine:test"


class TestDeriveOrderMonth:
    def test_parses_month_abbreviation(self):
        assert _derive_order_month(["raw/orders/orders_apr_2025.xlsx"]) == "2025-04"

    def test_parses_iso_month_in_key(self):
        assert _derive_order_month(["raw/orders/orders_2025-04.csv"]) == "2025-04"

    def test_unknown_when_no_match(self):
        assert _derive_order_month(["raw/products/products.csv"]) == "unknown"


class TestHandler:
    @patch.dict("os.environ", {"STATE_MACHINE_ARN": _STATE_MACHINE_ARN})
    @patch("lambda_functions.start_pipeline.boto3")
    def test_skips_when_execution_running(self, mock_boto3):
        mock_sfn = MagicMock()
        mock_sfn.list_executions.return_value = {"executions": [{"executionArn": "arn:running"}]}
        mock_boto3.client.return_value = mock_sfn

        result = handler({"Records": []}, None)

        assert result["started"] is False
        mock_sfn.start_execution.assert_not_called()

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": _STATE_MACHINE_ARN})
    @patch("lambda_functions.start_pipeline.boto3")
    def test_starts_execution(self, mock_boto3):
        mock_sfn = MagicMock()
        mock_sfn.list_executions.return_value = {"executions": []}
        mock_sfn.start_execution.return_value = {"executionArn": "arn:new"}
        mock_boto3.client.return_value = mock_sfn

        event = {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "detail": {
                                "bucket": {"name": "lake-bucket"},
                                "object": {"key": "raw/orders/orders_apr_2025.xlsx"},
                            }
                        }
                    )
                }
            ]
        }

        result = handler(event, None)

        assert result["started"] is True
        mock_sfn.start_execution.assert_called_once()
        payload = json.loads(mock_sfn.start_execution.call_args.kwargs["input"])
        assert payload["bucket"] == "lake-bucket"
        assert payload["order_month"] == "2025-04"

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": _STATE_MACHINE_ARN})
    @patch("lambda_functions.start_pipeline.boto3")
    def test_returns_no_bucket_when_records_empty(self, mock_boto3):
        mock_sfn = MagicMock()
        mock_sfn.list_executions.return_value = {"executions": []}
        mock_boto3.client.return_value = mock_sfn

        result = handler({"Records": []}, None)

        assert result == {"started": False, "reason": "no_bucket"}
        mock_sfn.start_execution.assert_not_called()
