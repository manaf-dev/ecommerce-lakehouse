"""AWS Glue 5.0 PySpark ingest job.

Parametrized via ``--dataset`` to handle all three datasets:
  products     — CSV, no partitioning
  orders       — XLSX, partitioned by order_month
  order_items  — XLSX, partitioned by order_month (referential checks required)

Processing sequence (per contracts/glue-job-interface.md):
  1. List source files under raw_prefix
  2. Read files into a Spark DataFrame (schema-enforced)
  3. Derive ``order_month`` for orders/order_items
  4. Validate — split into valid_df / rejected_df
  5. Write rejected_df to quarantine (Parquet)
  6. Deduplicate valid_df within batch (Window over PK)
  7. MERGE valid_df into Delta table
  8. OPTIMIZE + ZORDER if zorder_cols configured
  9. Log final counts

Entry point for Glue runtime: ``main()`` — uses ``getResolvedOptions``.
Entry point for tests / local run: ``run_ingest(spark, args)``.
"""

from __future__ import annotations

import sys
from functools import reduce
from pathlib import Path

from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

from utils.delta_helpers import merge_to_delta, optimize_and_zorder
from utils.logger import get_logger
from utils.readers import read_csv_to_spark, read_xlsx_to_spark
from utils.schemas import DATASET_CONFIG
from utils.validation import validate_order_items, validate_orders, validate_products

# Columns computed in the job rather than read from source files.
_DERIVED_COLS: dict[str, set[str]] = {
    "orders": {"order_month"},
    "order_items": {"order_month"},
}


def _get_read_schema(dataset: str, schema: StructType) -> StructType:
    """Return a schema with derived columns removed (they are added post-read)."""
    excluded = _DERIVED_COLS.get(dataset, set())
    return StructType([f for f in schema.fields if f.name not in excluded])


def _list_files(raw_prefix: str) -> list[str]:
    """Return file paths under *raw_prefix* (S3 or local filesystem)."""
    if raw_prefix.startswith("s3://"):
        import boto3  # noqa: PLC0415

        from utils.s3_helpers import list_s3_objects  # noqa: PLC0415

        tail = raw_prefix[len("s3://") :]
        bucket, _, prefix = tail.partition("/")
        client = boto3.client("s3")
        return [f"s3://{bucket}/{k}" for k in list_s3_objects(client, bucket, prefix)]
    else:
        p = Path(raw_prefix)
        return sorted(str(f) for f in p.glob("*") if f.is_file()) if p.exists() else []


def run_ingest(spark: object, args: dict) -> dict:
    """Core ingest logic — callable from tests without a Glue runtime.

    Args:
        spark: Active SparkSession.
        args: Parameter dict; required keys vary by dataset (see module docstring).

    Returns:
        Counts dict with keys: ``read``, ``valid``, ``rejected``, ``written``.
    """
    dataset: str = args["dataset"]
    raw_prefix: str = args["raw_prefix"]
    target_path: str = args["target_path"]
    quarantine_path: str = args["quarantine_path"]
    run_id: str = args.get("run_id", "local-run")

    logger = get_logger("ingest_delta", dataset=dataset, run_id=run_id)
    logger.info("Starting ingest_delta")

    cfg = DATASET_CONFIG[dataset]
    schema = cfg["schema"]
    pk: str = cfg["pk"]
    source_format: str = cfg["source_format"]
    partition_by: str | None = cfg["partition_by"]
    zorder_cols: list[str] = cfg["zorder_cols"]

    # ── 1. List source files ──────────────────────────────────────────────────
    files = _list_files(raw_prefix)
    logger.info(f"Read {len(files)} files from {raw_prefix}")

    if not files:
        logger.info("No files found. Exiting cleanly.")
        return {"read": 0, "valid": 0, "rejected": 0, "written": 0}

    # ── 2. Read source files ──────────────────────────────────────────────────
    read_schema = _get_read_schema(dataset, schema)

    if source_format == "csv":
        df = read_csv_to_spark(spark, raw_prefix, read_schema)
    else:
        # XLSX: read each file then union (multi-file support)
        dfs = [read_xlsx_to_spark(spark, f, read_schema) for f in files]
        df = reduce(lambda a, b: a.union(b), dfs)

    # ── 3. Derive order_month ─────────────────────────────────────────────────
    if dataset in _DERIVED_COLS:
        df = df.withColumn("order_month", F.date_format(F.col("date"), "yyyy-MM"))

    total = df.count()
    logger.info(f"Read: {total}")

    # ── 4. Validate ───────────────────────────────────────────────────────────
    if dataset == "products":
        valid_df, rejected_df = validate_products(df)
    elif dataset == "orders":
        valid_df, rejected_df = validate_orders(df)
    else:  # order_items
        orders_path = args.get("orders_path") or ""
        products_path = args.get("products_path") or ""
        if not orders_path or not products_path:
            raise ValueError(
                f"order_items requires --orders_path and --products_path; "
                f"got orders_path={orders_path!r}, products_path={products_path!r}"
            )
        orders_delta = spark.read.format("delta").load(orders_path)  # type: ignore[attr-defined]
        products_delta = spark.read.format("delta").load(products_path)  # type: ignore[attr-defined]
        valid_df, rejected_df = validate_order_items(df, orders_delta, products_delta)

    rejected_count = rejected_df.count()
    valid_count = valid_df.count()
    logger.info(f"Read: {total}, Valid: {valid_count}, Rejected: {rejected_count}")

    # ── 5. Write quarantine ───────────────────────────────────────────────────
    if rejected_count > 0:
        (
            rejected_df.write.mode("append")
            .format("parquet")
            .save(f"{quarantine_path}/run_id={run_id}/")
        )
        logger.info(f"Quarantined {rejected_count} rows")

    if valid_count == 0:
        logger.info("All rows rejected. No Delta write.")
        return {"read": total, "valid": 0, "rejected": rejected_count, "written": 0}

    # ── 6. Deduplicate within batch (Window over PK by _ingested_at) ──────────
    valid_df = valid_df.withColumn("_ingested_at", F.current_timestamp())
    w = Window.partitionBy(pk).orderBy(F.col("_ingested_at").desc())
    valid_df = (
        valid_df.withColumn("_rn", F.row_number().over(w))
        .filter(F.col("_rn") == 1)
        .drop("_rn", "_ingested_at")
    )

    # ── 7. MERGE into Delta ───────────────────────────────────────────────────
    merge_to_delta(spark, valid_df, target_path, pk=pk, partition_by=partition_by)
    logger.info(f"MERGE complete. Written: {valid_count}")

    # ── 8. OPTIMIZE + ZORDER ─────────────────────────────────────────────────
    if zorder_cols:
        optimize_and_zorder(spark, target_path, zorder_cols)
        logger.info("OPTIMIZE+ZORDER complete")

    return {
        "read": total,
        "valid": valid_count,
        "rejected": rejected_count,
        "written": valid_count,
    }


def main() -> None:
    """AWS Glue 5.0 PySpark entry point. Falls back to local Spark for debugging."""
    try:
        from awsglue.context import GlueContext  # noqa: PLC0415
        from awsglue.job import Job  # noqa: PLC0415
        from awsglue.utils import getResolvedOptions  # noqa: PLC0415
        from pyspark.context import SparkContext  # noqa: PLC0415

        params = getResolvedOptions(
            sys.argv,
            ["JOB_NAME", "dataset", "raw_prefix", "target_path", "quarantine_path", "run_id"],
        )
        sc = SparkContext()
        glue_ctx = GlueContext(sc)
        spark = glue_ctx.spark_session
        job = Job(glue_ctx)
        job.init(params["JOB_NAME"], params)

        try:
            extras = getResolvedOptions(sys.argv, ["products_path", "orders_path"])
            params.update(extras)
        except SystemExit:
            pass  # not order_items; paths are absent and will be validated in run_ingest if needed

        run_ingest(spark, params)
        job.commit()

    except ImportError:
        # Local / CI execution without AWS Glue runtime
        from pyspark.sql import SparkSession  # noqa: PLC0415

        local_spark = (
            SparkSession.builder.master("local[2]")
            .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.2.0")
            .getOrCreate()
        )
        import argparse  # noqa: PLC0415

        parser = argparse.ArgumentParser(description="Local ingest_delta runner")
        for flag in ["--dataset", "--raw_prefix", "--target_path", "--quarantine_path", "--run_id"]:
            parser.add_argument(flag)
        parser.add_argument("--products_path", default="")
        parser.add_argument("--orders_path", default="")
        ns = parser.parse_args()
        run_ingest(local_spark, {k: v for k, v in vars(ns).items() if v is not None})


if __name__ == "__main__":
    main()
