"""Integration tests for ingest_delta.py — orders dataset (XLSX).

Uses local temp directories. pandas nullable Int64 dtype is used when writing
test XLSX files so that None values survive the Excel round-trip.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from glue_jobs.ingest_delta import run_ingest

# Base valid order row (without order_month — derived by the job)
_VALID_ORDER: dict = {
    "order_id": 1,
    "order_num": None,
    "user_id": 1,
    "order_timestamp": datetime(2025, 4, 1, 10, 0),
    "total_amount": 100.0,
    "date": date(2025, 4, 1),
}


def _write_orders_xlsx(path: Path, rows: list[dict]) -> None:
    """Write *rows* to an XLSX file using nullable pandas dtypes."""
    df = pd.DataFrame(rows)
    for col in ("order_id", "order_num", "user_id"):
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(str(path), index=False)


def _ingest_args(tmp_path: Path, **overrides) -> dict:
    return {
        "dataset": "orders",
        "raw_prefix": str(tmp_path / "raw" / "orders"),
        "target_path": str(tmp_path / "delta" / "orders"),
        "quarantine_path": str(tmp_path / "quarantine" / "orders"),
        "run_id": "test-orders",
        **overrides,
    }


class TestIngestOrders:
    def test_mixed_valid_invalid_orders(self, spark, s3_client, tmp_path):
        """5 valid + 3 null-order_id rows: Delta gets 5, quarantine gets 3."""
        raw_dir = tmp_path / "raw" / "orders"
        raw_dir.mkdir(parents=True)

        valid_rows = [{**_VALID_ORDER, "order_id": i, "user_id": i} for i in range(1, 6)]
        invalid_rows = [
            {**_VALID_ORDER, "order_id": None, "user_id": 10},
            {**_VALID_ORDER, "order_id": None, "user_id": 11},
            {**_VALID_ORDER, "order_id": None, "user_id": 12},
        ]
        _write_orders_xlsx(raw_dir / "orders.xlsx", valid_rows + invalid_rows)

        args = _ingest_args(tmp_path)
        result = run_ingest(spark, args)

        assert result["valid"] == 5
        assert result["rejected"] == 3
        assert spark.read.format("delta").load(args["target_path"]).count() == 5

    def test_zero_silent_drops(self, spark, s3_client, tmp_path):
        """valid_count + rejected_count equals total_read_count (no silent drops)."""
        raw_dir = tmp_path / "raw" / "orders"
        raw_dir.mkdir(parents=True)
        rows = [
            {**_VALID_ORDER, "order_id": 1, "user_id": 1},
            {**_VALID_ORDER, "order_id": None, "user_id": 2},
            {**_VALID_ORDER, "order_id": 3, "total_amount": 0.0, "user_id": 3},
        ]
        _write_orders_xlsx(raw_dir / "orders.xlsx", rows)

        result = run_ingest(spark, _ingest_args(tmp_path))
        assert result["valid"] + result["rejected"] == result["read"]

    def test_multi_rule_failure_row(self, spark, s3_client, tmp_path):
        """Row with null user_id AND total_amount=0 lands in quarantine with both reasons."""
        raw_dir = tmp_path / "raw" / "orders"
        raw_dir.mkdir(parents=True)
        rows = [{**_VALID_ORDER, "order_id": 1, "user_id": None, "total_amount": 0.0}]
        _write_orders_xlsx(raw_dir / "orders.xlsx", rows)

        args = _ingest_args(tmp_path)
        result = run_ingest(spark, args)

        assert result["rejected"] == 1
        q_path = f"{args['quarantine_path']}/run_id={args['run_id']}/"
        quarantine_df = spark.read.parquet(q_path)
        reason = quarantine_df.collect()[0]["_rejection_reason"]
        assert "user_id null or <= 0" in reason
        assert "total_amount not > 0" in reason

    def test_all_invalid_batch_no_error(self, spark, s3_client, tmp_path):
        """All invalid rows: job exits cleanly with written=0."""
        raw_dir = tmp_path / "raw" / "orders"
        raw_dir.mkdir(parents=True)
        rows = [
            {**_VALID_ORDER, "order_id": None, "user_id": 1},
            {**_VALID_ORDER, "order_id": None, "user_id": 2},
        ]
        _write_orders_xlsx(raw_dir / "orders.xlsx", rows)

        result = run_ingest(spark, _ingest_args(tmp_path))
        assert result["written"] == 0
        assert result["rejected"] == 2
