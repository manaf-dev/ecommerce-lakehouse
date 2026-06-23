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
    """Register (or refresh) a Delta table in the Glue Data Catalog via the Glue API.

    Uses the same table format that Athena DDL produces for Delta tables:
    - table_type = "delta" (lowercase — uppercase breaks Athena's Delta reader)
    - spark.sql.sources.schema.part.0 = full Spark schema JSON
    - No 'path' parameter (Athena uses StorageDescriptor.Location)
    """
    import boto3  # noqa: PLC0415
    from botocore.exceptions import ClientError  # noqa: PLC0415
    from pyspark.sql import types as T  # noqa: PLC0415

    from delta.tables import DeltaTable  # noqa: PLC0415

    dt = DeltaTable.forPath(spark, target_path)
    history_row = dt.history(1).select("version", "timestamp").collect()[0]
    delta_version = str(history_row["version"])
    delta_ts_ms = str(int(history_row["timestamp"].timestamp() * 1000))

    schema = dt.toDF().schema

    def _glue_type(dt_: object) -> str:
        if isinstance(dt_, T.DecimalType):
            return f"decimal({dt_.precision},{dt_.scale})"
        return {
            T.StringType: "string",
            T.IntegerType: "int",
            T.LongType: "bigint",
            T.DoubleType: "double",
            T.FloatType: "float",
            T.BooleanType: "boolean",
            T.DateType: "date",
            T.TimestampType: "timestamp",
        }.get(type(dt_), "string")

    table_input = {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "EXTERNAL": "TRUE",
            "table_type": "delta",
            "spark.sql.sources.provider": "delta",
            "spark.sql.sources.schema.numParts": "1",
            "spark.sql.sources.schema.part.0": schema.json(),
            "spark.sql.partitionProvider": "catalog",
            "delta.lastUpdateVersion": delta_version,
            "delta.lastCommitTimestamp": delta_ts_ms,
        },
        "StorageDescriptor": {
            "Columns": [{"Name": f.name, "Type": _glue_type(f.dataType)} for f in schema.fields],  # type: ignore[arg-type]
            "Location": target_path,
            "InputFormat": "org.apache.hadoop.mapred.SequenceFileInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveSequenceFileOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
            },
            "Compressed": False,
            "NumberOfBuckets": -1,
        },
    }

    glue = boto3.client("glue")
    try:
        glue.create_table(DatabaseName=catalog_db, TableInput=table_input)
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            glue.update_table(DatabaseName=catalog_db, TableInput=table_input)
        else:
            raise


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
