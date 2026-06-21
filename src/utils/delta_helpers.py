"""Delta Lake MERGE + OPTIMIZE helpers."""

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
    """MERGE source_df into the Delta table at target_path on pk (+ partition when set)."""
    from delta.tables import DeltaTable  # noqa: PLC0415

    if not DeltaTable.isDeltaTable(spark, target_path):
        writer = source_df.write.format("delta").mode("overwrite")
        if partition_by:
            writer = writer.partitionBy(partition_by)
        writer.save(target_path)
        return

    merge_predicate = f"t.{pk} = s.{pk}"
    if partition_by:
        merge_predicate = f"{merge_predicate} AND t.{partition_by} = s.{partition_by}"

    (
        DeltaTable.forPath(spark, target_path)
        .alias("t")
        .merge(source_df.alias("s"), merge_predicate)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def register_delta_table(
    spark: SparkSession,
    target_path: str,
    catalog_db: str,
    table_name: str,
) -> None:
    """Register (or refresh) a Delta table in the Glue Data Catalog."""
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {catalog_db}.{table_name}
        USING DELTA
        LOCATION '{target_path}'
        """
    )


def optimize_and_zorder(
    spark: SparkSession,
    target_path: str,
    zorder_cols: list[str],
) -> None:
    """Run OPTIMIZE + ZORDER on a Delta table when columns are configured."""
    if not zorder_cols:
        return
    from delta.tables import DeltaTable  # noqa: PLC0415

    DeltaTable.forPath(spark, target_path).optimize().executeZOrderBy(*zorder_cols)
