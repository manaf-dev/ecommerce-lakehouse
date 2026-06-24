"""Delta Lake MERGE + OPTIMIZE helpers."""

from __future__ import annotations

import time
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
    target_path: str,
    catalog_db: str,
    table_name: str,
    workgroup: str = "primary",
) -> None:
    """Register (or refresh) a Delta table in the Glue Data Catalog via Athena DDL.

    Uses CREATE EXTERNAL TABLE ... TBLPROPERTIES ('table_type'='DELTA'), which is the
    approach Athena engine v3 natively recognises for Delta Lake tables. The Glue API
    approach produces tables with subtle metadata differences that break Athena's Delta
    reader, so we drop any stale entry first and recreate via DDL.
    """
    import boto3  # noqa: PLC0415
    from botocore.exceptions import ClientError  # noqa: PLC0415

    # Remove any stale entry (Glue API or prior DDL) before recreating.
    glue = boto3.client("glue")
    try:
        glue.delete_table(DatabaseName=catalog_db, Name=table_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise

    bucket = target_path.split("/")[2]
    s3_output = f"s3://{bucket}/athena-results/glue-ddl-tmp/"
    athena = boto3.client("athena")
    resp = athena.start_query_execution(
        QueryString=(
            f"CREATE EXTERNAL TABLE `{table_name}` "
            f"LOCATION '{target_path}' "
            f"TBLPROPERTIES ('table_type'='DELTA')"
        ),
        QueryExecutionContext={"Database": catalog_db},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": s3_output},
    )
    qeid = resp["QueryExecutionId"]
    for _ in range(30):
        status = athena.get_query_execution(QueryExecutionId=qeid)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            return
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Athena CREATE TABLE failed ({state}): {reason}")
        time.sleep(2)
    raise TimeoutError(f"Athena DDL timed out for {table_name}")


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
