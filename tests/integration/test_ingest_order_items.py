"""Integration tests for ingest_delta.py — order_items dataset (XLSX).

Pre-populates the orders and products Delta tables (referential check precondition)
then exercises the full ingest flow for order_items.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from glue_jobs.ingest_delta import run_ingest
from utils.delta_helpers import merge_to_delta
from utils.schemas import ORDERS_SCHEMA, PRODUCTS_SCHEMA

# ── Reference data ─────────────────────────────────────────────────────────────
_VALID_PRODUCT = (1, 1, "Beverages", "Cola")
_VALID_ORDER = (1, None, 10, datetime(2025, 4, 1, 10), 100.0, date(2025, 4, 1), "2025-04")

# A valid order_item row (no order_month — derived by the job)
_VALID_ITEM: dict = {
    "id": 1,
    "order_id": 1,
    "user_id": 10,
    "days_since_prior_order": None,
    "product_id": 1,
    "add_to_cart_order": 1,
    "reordered": 0,
    "order_timestamp": None,
    "date": date(2025, 4, 1),
}


def _setup_reference_tables(spark, tmp_path: Path) -> tuple[str, str]:
    """Write products + orders Delta tables and return their paths."""
    products_path = str(tmp_path / "delta" / "products")
    orders_path = str(tmp_path / "delta" / "orders")

    products_df = spark.createDataFrame([_VALID_PRODUCT], schema=PRODUCTS_SCHEMA)
    orders_df = spark.createDataFrame([_VALID_ORDER], schema=ORDERS_SCHEMA)

    merge_to_delta(spark, products_df, products_path, pk="product_id")
    merge_to_delta(spark, orders_df, orders_path, pk="order_id", partition_by="order_month")

    return products_path, orders_path


def _write_order_items_xlsx(path: Path, rows: list[dict]) -> None:
    """Write order_items rows to XLSX using nullable pandas dtypes."""
    df = pd.DataFrame(rows)
    for col in ("id", "order_id", "user_id", "product_id", "add_to_cart_order", "reordered"):
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(str(path), index=False)


def _ingest_args(tmp_path: Path, products_path: str, orders_path: str, **overrides) -> dict:
    return {
        "dataset": "order_items",
        "raw_prefix": str(tmp_path / "raw" / "order_items"),
        "target_path": str(tmp_path / "delta" / "order_items"),
        "quarantine_path": str(tmp_path / "quarantine" / "order_items"),
        "run_id": "test-oi",
        "products_path": products_path,
        "orders_path": orders_path,
        **overrides,
    }


class TestIngestOrderItems:
    def test_referential_integrity_order_id(self, spark, s3_client, tmp_path):
        """order_item with unknown order_id → quarantined with correct reason."""
        products_path, orders_path = _setup_reference_tables(spark, tmp_path)
        raw_dir = tmp_path / "raw" / "order_items"
        raw_dir.mkdir(parents=True)

        rows = [{**_VALID_ITEM, "id": 1, "order_id": 999}]  # 999 not in orders
        _write_order_items_xlsx(raw_dir / "oi.xlsx", rows)

        args = _ingest_args(tmp_path, products_path, orders_path)
        result = run_ingest(spark, args)

        assert result["rejected"] == 1
        assert result["written"] == 0

        q_path = f"{args['quarantine_path']}/run_id={args['run_id']}/"
        reason = spark.read.parquet(q_path).collect()[0]["_rejection_reason"]
        assert "order_id not found in orders" in reason

    def test_referential_integrity_product_id(self, spark, s3_client, tmp_path):
        """order_item with unknown product_id → quarantined."""
        products_path, orders_path = _setup_reference_tables(spark, tmp_path)
        raw_dir = tmp_path / "raw" / "order_items"
        raw_dir.mkdir(parents=True)

        rows = [{**_VALID_ITEM, "id": 1, "product_id": 999}]  # 999 not in products
        _write_order_items_xlsx(raw_dir / "oi.xlsx", rows)

        args = _ingest_args(tmp_path, products_path, orders_path)
        result = run_ingest(spark, args)

        assert result["rejected"] == 1
        q_path = f"{args['quarantine_path']}/run_id={args['run_id']}/"
        reason = spark.read.parquet(q_path).collect()[0]["_rejection_reason"]
        assert "product_id not found in products" in reason

    def test_user_id_mismatch(self, spark, s3_client, tmp_path):
        """order_item user_id mismatch with order's user_id → quarantined."""
        products_path, orders_path = _setup_reference_tables(spark, tmp_path)
        raw_dir = tmp_path / "raw" / "order_items"
        raw_dir.mkdir(parents=True)

        rows = [{**_VALID_ITEM, "id": 1, "user_id": 99}]  # order's user_id is 10
        _write_order_items_xlsx(raw_dir / "oi.xlsx", rows)

        args = _ingest_args(tmp_path, products_path, orders_path)
        result = run_ingest(spark, args)

        assert result["rejected"] == 1
        q_path = f"{args['quarantine_path']}/run_id={args['run_id']}/"
        reason = spark.read.parquet(q_path).collect()[0]["_rejection_reason"]
        assert "user_id mismatch for order_id" in reason

    def test_valid_order_items_merged(self, spark, s3_client, tmp_path):
        """All-valid batch: all rows in Delta, quarantine empty."""
        products_path, orders_path = _setup_reference_tables(spark, tmp_path)
        raw_dir = tmp_path / "raw" / "order_items"
        raw_dir.mkdir(parents=True)

        rows = [{**_VALID_ITEM, "id": i, "add_to_cart_order": i} for i in range(1, 4)]
        _write_order_items_xlsx(raw_dir / "oi.xlsx", rows)

        args = _ingest_args(tmp_path, products_path, orders_path)
        result = run_ingest(spark, args)

        assert result["written"] == 3
        assert result["rejected"] == 0
        assert spark.read.format("delta").load(args["target_path"]).count() == 3

    def test_idempotency_order_items(self, spark, s3_client, tmp_path):
        """Same XLSX file ingested twice: Delta row count unchanged (MERGE idempotency)."""
        products_path, orders_path = _setup_reference_tables(spark, tmp_path)
        raw_dir = tmp_path / "raw" / "order_items"
        raw_dir.mkdir(parents=True)

        rows = [{**_VALID_ITEM, "id": i, "add_to_cart_order": i} for i in range(1, 4)]
        _write_order_items_xlsx(raw_dir / "oi.xlsx", rows)

        args = _ingest_args(tmp_path, products_path, orders_path)
        run_ingest(spark, args)
        count_1 = spark.read.format("delta").load(args["target_path"]).count()

        run_ingest(spark, args)
        count_2 = spark.read.format("delta").load(args["target_path"]).count()

        assert count_1 == count_2 == 3
