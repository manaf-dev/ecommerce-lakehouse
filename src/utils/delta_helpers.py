"""Delta Lake MERGE + OPTIMIZE helpers.

merge_to_delta   — upsert a source DataFrame into a Delta table on a PK.
optimize_and_zorder — compact and Z-order a Delta table after MERGE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession  # pragma: no cover


def merge_to_delta(
    spark: SparkSession,
    source_df: DataFrame,
    target_path: str,
    pk: str,
    partition_by: str | None = None,
) -> None:
    """MERGE source_df into the Delta table at target_path on pk.

    If the Delta table does not yet exist at target_path, it is created with
    an initial write (partitioned by partition_by if given).  Subsequent calls
    perform a whenMatchedUpdateAll / whenNotMatchedInsertAll MERGE, which is
    idempotent for the same source batch.

    Args:
        spark: Active SparkSession with Delta extensions configured.
        source_df: DataFrame to merge in.
        target_path: Absolute S3 or local path to the Delta table.
        pk: Primary key column name used as the merge predicate.
        partition_by: Optional column to partition the Delta table by.
    """
    from delta.tables import DeltaTable  # noqa: PLC0415

    if not DeltaTable.isDeltaTable(spark, target_path):
        writer = source_df.write.format("delta").mode("overwrite")
        if partition_by:
            writer = writer.partitionBy(partition_by)
        writer.save(target_path)
        return

    (
        DeltaTable.forPath(spark, target_path)
        .alias("t")
        .merge(source_df.alias("s"), f"t.{pk} = s.{pk}")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def optimize_and_zorder(
    spark: SparkSession,
    target_path: str,
    zorder_cols: list[str],
) -> None:
    """Run OPTIMIZE + ZORDER on a Delta table.

    Skips silently when zorder_cols is empty (e.g. products table).

    Args:
        spark: Active SparkSession with Delta extensions configured.
        target_path: Absolute S3 or local path to the Delta table.
        zorder_cols: Columns to Z-order by.  Empty list → no-op.
    """
    if not zorder_cols:
        return
    from delta.tables import DeltaTable  # noqa: PLC0415

    DeltaTable.forPath(spark, target_path).optimize().executeZOrderBy(*zorder_cols)
