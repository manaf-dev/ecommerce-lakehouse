"""Unit tests for src/utils/delta_helpers.py — MERGE and OPTIMIZE."""

from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from utils.delta_helpers import merge_to_delta, optimize_and_zorder

_SCHEMA = StructType(
    [
        StructField("pk", IntegerType(), nullable=False),
        StructField("value", StringType(), nullable=True),
    ]
)


class TestMergeToDelta:
    def test_merge_inserts_new_row(self, spark, tmp_path):
        """First merge into empty path creates the Delta table with 1 row."""
        path = str(tmp_path / "delta_table")
        source = spark.createDataFrame([(1, "hello")], schema=_SCHEMA)
        merge_to_delta(spark, source, path, pk="pk")

        result = spark.read.format("delta").load(path)
        assert result.count() == 1

    def test_merge_updates_existing_row(self, spark, tmp_path):
        """Merge updates an existing row when the PK matches."""
        path = str(tmp_path / "delta_table")
        initial = spark.createDataFrame([(1, "old")], schema=_SCHEMA)
        merge_to_delta(spark, initial, path, pk="pk")

        updated = spark.createDataFrame([(1, "new")], schema=_SCHEMA)
        merge_to_delta(spark, updated, path, pk="pk")

        rows = spark.read.format("delta").load(path).collect()
        assert len(rows) == 1
        assert rows[0]["value"] == "new"

    def test_merge_idempotent(self, spark, tmp_path):
        """Running the same merge twice leaves the row count unchanged."""
        path = str(tmp_path / "delta_table")
        source = spark.createDataFrame([(1, "a"), (2, "b")], schema=_SCHEMA)

        merge_to_delta(spark, source, path, pk="pk")
        count_after_first = spark.read.format("delta").load(path).count()

        merge_to_delta(spark, source, path, pk="pk")
        count_after_second = spark.read.format("delta").load(path).count()

        assert count_after_first == count_after_second == 2

    def test_merge_inserts_new_and_keeps_existing(self, spark, tmp_path):
        """Merge inserts new rows and updates matching rows in the same call."""
        path = str(tmp_path / "delta_table")
        initial = spark.createDataFrame([(1, "old_1"), (2, "old_2")], schema=_SCHEMA)
        merge_to_delta(spark, initial, path, pk="pk")

        source = spark.createDataFrame([(1, "updated_1"), (3, "new_3")], schema=_SCHEMA)
        merge_to_delta(spark, source, path, pk="pk")

        rows_collected = spark.read.format("delta").load(path).collect()
        result = {r["pk"]: r["value"] for r in rows_collected}
        assert result == {1: "updated_1", 2: "old_2", 3: "new_3"}

    def test_merge_with_partition_by(self, spark, tmp_path):
        """Initial write respects the partition_by argument."""
        path = str(tmp_path / "delta_partitioned")
        from pyspark.sql.types import StructType

        schema = StructType(
            [
                StructField("pk", IntegerType(), nullable=False),
                StructField("month", StringType(), nullable=False),
                StructField("value", StringType(), nullable=True),
            ]
        )
        source = spark.createDataFrame([(1, "2025-04", "x"), (2, "2025-04", "y")], schema=schema)
        merge_to_delta(spark, source, path, pk="pk", partition_by="month")

        result = spark.read.format("delta").load(path)
        assert result.count() == 2


class TestOptimizeAndZorder:
    def test_optimize_no_zorder_cols_is_noop(self, spark, tmp_path):
        """optimize_and_zorder with empty list returns None without error."""
        path = str(tmp_path / "delta_noop")
        source = spark.createDataFrame([(1, "a")], schema=_SCHEMA)
        merge_to_delta(spark, source, path, pk="pk")

        result = optimize_and_zorder(spark, path, zorder_cols=[])
        assert result is None

    def test_optimize_with_zorder_cols(self, spark, tmp_path):
        """optimize_and_zorder with a valid column succeeds without error."""
        path = str(tmp_path / "delta_zorder")
        source = spark.createDataFrame([(i, f"v{i}") for i in range(1, 20)], schema=_SCHEMA)
        merge_to_delta(spark, source, path, pk="pk")

        # Should complete without raising
        optimize_and_zorder(spark, path, zorder_cols=["pk"])
