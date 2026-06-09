"""CSV and XLSX → Spark DataFrame readers.

read_dataset() dispatches based on source_format from DATASET_CONFIG.
XLSX files may contain multiple sheets; all sheets are concatenated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession  # pragma: no cover
    from pyspark.sql.types import StructType  # pragma: no cover


def read_csv_to_spark(
    spark: SparkSession,
    path: str,
    schema: StructType,
) -> DataFrame:
    """Read a CSV file (or prefix) into a Spark DataFrame.

    Args:
        spark: Active SparkSession.
        path: S3 path or local path to the CSV file(s).
        schema: Target StructType — enforced at read time.

    Returns:
        Spark DataFrame with the given schema.
    """
    return spark.read.schema(schema).option("header", "true").csv(path)


def read_xlsx_to_spark(
    spark: SparkSession,
    path: str,
    schema: StructType,
) -> DataFrame:
    """Read an XLSX file into a Spark DataFrame.

    All sheets in the workbook are concatenated. Empty sheets are silently
    skipped. Reads the file on the driver via pandas+openpyxl, then
    distributes the combined DataFrame to Spark workers.

    Args:
        spark: Active SparkSession.
        path: Local path to the XLSX file (must be accessible on the driver).
        schema: Target StructType — used when creating the Spark DataFrame.

    Returns:
        Spark DataFrame containing rows from all sheets.
    """
    all_sheets: dict[str, pd.DataFrame] = pd.read_excel(
        path,
        sheet_name=None,
        engine="openpyxl",
    )
    non_empty = [df for df in all_sheets.values() if not df.empty]
    if not non_empty:
        return spark.createDataFrame([], schema=schema)
    combined = pd.concat(non_empty, ignore_index=True)
    # Replace pandas NaN with Python None so Spark maps them to null correctly.
    # Without this, NaN in integer columns raises a type-cast error.
    combined = combined.where(pd.notna(combined), other=None)
    return spark.createDataFrame(combined, schema=schema)


def read_dataset(
    spark: SparkSession,
    path: str,
    source_format: str,
    schema: StructType,
) -> DataFrame:
    """Dispatch to the correct reader based on source_format.

    Args:
        spark: Active SparkSession.
        path: Path to the source file.
        source_format: ``"csv"`` or ``"xlsx"``.
        schema: Target StructType.

    Returns:
        Spark DataFrame.

    Raises:
        ValueError: If source_format is not ``"csv"`` or ``"xlsx"``.
    """
    if source_format == "csv":
        return read_csv_to_spark(spark, path, schema)
    if source_format == "xlsx":
        return read_xlsx_to_spark(spark, path, schema)
    raise ValueError(f"Unsupported source_format: {source_format!r}. Expected 'csv' or 'xlsx'.")
