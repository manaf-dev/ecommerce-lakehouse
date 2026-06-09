"""Integration tests for ingest_delta.py — products dataset (CSV).

Uses local temp directories for both source files and Delta tables so no
S3A JARs are required.  The s3_client fixture is included to initialise the
moto environment for any boto3 calls that may occur inside the job.
"""

from __future__ import annotations

from pathlib import Path

from glue_jobs.ingest_delta import run_ingest


def _write_products_csv(directory: Path, rows: list[tuple]) -> None:
    """Write a minimal products CSV to *directory*/products.csv."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["product_id,department_id,department,product_name"] + [
        ",".join("" if v is None else str(v) for v in r) for r in rows
    ]
    (directory / "products.csv").write_text("\n".join(lines) + "\n")


def _ingest_args(tmp_path: Path, **overrides) -> dict:
    return {
        "dataset": "products",
        "raw_prefix": str(tmp_path / "raw" / "products"),
        "target_path": str(tmp_path / "delta" / "products"),
        "quarantine_path": str(tmp_path / "quarantine" / "products"),
        "run_id": "test-products",
        **overrides,
    }


class TestIngestProducts:
    def test_valid_products_batch(self, spark, s3_client, tmp_path):
        """All-valid CSV: Delta table receives correct row count."""
        raw = tmp_path / "raw" / "products"
        _write_products_csv(
            raw,
            [(1, 1, "Beverages", "Cola"), (2, 1, "Beverages", "Water"), (3, 2, "Snacks", "Chips")],
        )

        args = _ingest_args(tmp_path)
        result = run_ingest(spark, args)

        delta_df = spark.read.format("delta").load(args["target_path"])
        assert delta_df.count() == 3
        assert result == {"read": 3, "valid": 3, "rejected": 0, "written": 3}

    def test_empty_prefix_exits_cleanly(self, spark, s3_client, tmp_path):
        """Empty source directory: job returns zeros without creating Delta table."""
        empty_dir = tmp_path / "raw" / "products"
        empty_dir.mkdir(parents=True)

        args = _ingest_args(tmp_path)
        result = run_ingest(spark, args)

        assert result == {"read": 0, "valid": 0, "rejected": 0, "written": 0}
        assert not Path(args["target_path"]).exists()

    def test_idempotency_products(self, spark, s3_client, tmp_path):
        """Running the same file twice: Delta row count is identical after each run."""
        raw = tmp_path / "raw" / "products"
        _write_products_csv(raw, [(1, 1, "Beverages", "Cola"), (2, 2, "Snacks", "Chips")])

        args = _ingest_args(tmp_path)
        run_ingest(spark, args)
        count_1 = spark.read.format("delta").load(args["target_path"]).count()

        run_ingest(spark, args)
        count_2 = spark.read.format("delta").load(args["target_path"]).count()

        assert count_1 == count_2 == 2

    def test_invalid_rows_quarantined(self, spark, s3_client, tmp_path):
        """Rows with null product_id → quarantine, valid rows → Delta."""
        raw = tmp_path / "raw" / "products"
        _write_products_csv(
            raw,
            [
                (1, 1, "Beverages", "Cola"),  # valid
                (None, 2, "Snacks", "Chips"),  # invalid: null product_id
                (0, 3, "Dairy", "Milk"),  # invalid: product_id = 0
            ],
        )

        args = _ingest_args(tmp_path)
        result = run_ingest(spark, args)

        assert result["valid"] == 1
        assert result["rejected"] == 2

    def test_duplicate_pk_within_batch_deduped(self, spark, s3_client, tmp_path):
        """Duplicate product_id in source: only one row survives MERGE."""
        raw = tmp_path / "raw" / "products"
        _write_products_csv(
            raw,
            [
                (1, 1, "Beverages", "Cola"),
                (1, 1, "Beverages", "Cola-duplicate"),  # duplicate PK
                (2, 2, "Snacks", "Chips"),
            ],
        )

        args = _ingest_args(tmp_path)
        run_ingest(spark, args)

        delta_count = spark.read.format("delta").load(args["target_path"]).count()
        assert delta_count == 2  # PK=1 deduplicated to one row
