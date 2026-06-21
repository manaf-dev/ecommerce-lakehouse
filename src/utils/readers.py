"""CSV and XLSX → Spark DataFrame readers.

read_dataset() dispatches based on source_format from DATASET_CONFIG.
XLSX files may contain multiple sheets; all sheets are concatenated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
from pyspark.sql.types import (
    DateType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    ShortType,
    StringType,
    StructType,
    TimestampType,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession  # pragma: no cover


def _sanitize_value(value: Any) -> Any:
    """Map pandas/NumPy null sentinels to Python None for Spark rows."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return value
    return value


def _cast_value_for_spark(value: Any, data_type: Any) -> Any:
    """Cast a single cell value to a Python type Spark accepts for *data_type*."""
    value = _sanitize_value(value)
    if value is None:
        return None
    if isinstance(data_type, TimestampType):
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        return pd.to_datetime(value).to_pydatetime()
    if isinstance(data_type, DateType):
        if hasattr(value, "year") and not isinstance(value, pd.Timestamp):
            return value
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    if isinstance(data_type, (IntegerType, LongType, ShortType)):
        return int(float(value))
    if isinstance(data_type, (DoubleType, FloatType)):
        return float(value)
    if isinstance(data_type, StringType):
        return str(value)
    return value


def _coerce_pandas_types(df: pd.DataFrame, schema: StructType) -> pd.DataFrame:
    """Coerce pandas columns to Spark-compatible Python values."""
    out = df.copy()
    for field in schema.fields:
        if field.name not in out.columns:
            continue
        col = field.name
        if isinstance(field.dataType, TimestampType):
            out[col] = pd.to_datetime(out[col], errors="coerce")
        elif isinstance(field.dataType, DateType):
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.date
        elif isinstance(field.dataType, (IntegerType, LongType, ShortType)):
            numeric = pd.to_numeric(out[col], errors="coerce")
            out[col] = [int(v) if pd.notna(v) else None for v in numeric]
        elif isinstance(field.dataType, (DoubleType, FloatType)):
            numeric = pd.to_numeric(out[col], errors="coerce")
            out[col] = [float(v) if pd.notna(v) else None for v in numeric]
    return out


def _rows_for_schema(df: pd.DataFrame, schema: StructType) -> list[dict[str, Any]]:
    """Align pandas columns to schema order and emit Spark-safe row dicts."""
    aligned = df.copy()
    for field in schema.fields:
        if field.name not in aligned.columns:
            aligned[field.name] = None
    ordered = aligned[[field.name for field in schema.fields]]
    return [
        {
            field.name: _cast_value_for_spark(record[field.name], field.dataType)
            for field in schema.fields
        }
        for record in ordered.to_dict("records")
    ]


def read_csv_to_spark(
    spark: SparkSession,
    path: str,
    schema: StructType,
) -> DataFrame:
    """Read a CSV file (or prefix) into a Spark DataFrame."""
    return spark.read.schema(schema).option("header", "true").csv(path)


def read_xlsx_to_spark(
    spark: SparkSession,
    path: str,
    schema: StructType,
) -> DataFrame:
    """Read an XLSX file into a Spark DataFrame."""
    all_sheets: dict[str, pd.DataFrame] = pd.read_excel(
        path,
        sheet_name=None,
        engine="openpyxl",
    )
    non_empty = [sheet_df for sheet_df in all_sheets.values() if not sheet_df.empty]
    if not non_empty:
        return spark.createDataFrame([], schema=schema)

    combined = pd.concat(non_empty, ignore_index=True)
    combined = _coerce_pandas_types(combined, schema)
    rows = _rows_for_schema(combined, schema)
    return spark.createDataFrame(rows, schema=schema)


def read_dataset(
    spark: SparkSession,
    path: str,
    source_format: str,
    schema: StructType,
) -> DataFrame:
    """Dispatch to the correct reader based on source_format."""
    if source_format == "csv":
        return read_csv_to_spark(spark, path, schema)
    if source_format == "xlsx":
        return read_xlsx_to_spark(spark, path, schema)
    raise ValueError(f"Unsupported source_format: {source_format!r}. Expected 'csv' or 'xlsx'.")
