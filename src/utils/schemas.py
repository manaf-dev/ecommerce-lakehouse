"""PySpark StructType schemas and the DATASET_CONFIG registry.

Each entry in DATASET_CONFIG drives the parametrized ingest_delta job:
  schema        — StructType for reading and writing
  pk            — merge key column name
  partition_by  — partition column (None = unpartitioned)
  zorder_cols   — columns to ZORDER after MERGE (empty = skip OPTIMIZE)
  source_format — "csv" | "xlsx"
"""

from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# ─── Products ─────────────────────────────────────────────────────────────────
PRODUCTS_SCHEMA = StructType(
    [
        StructField("product_id", IntegerType(), nullable=False),
        StructField("department_id", IntegerType(), nullable=False),
        StructField("department", StringType(), nullable=False),
        StructField("product_name", StringType(), nullable=False),
    ]
)

# ─── Orders ───────────────────────────────────────────────────────────────────
ORDERS_SCHEMA = StructType(
    [
        StructField("order_id", LongType(), nullable=False),
        StructField("order_num", LongType(), nullable=True),
        StructField("user_id", LongType(), nullable=False),
        StructField("order_timestamp", TimestampType(), nullable=False),
        StructField("total_amount", DoubleType(), nullable=False),
        StructField("date", DateType(), nullable=False),
        StructField("order_month", StringType(), nullable=False),
    ]
)

# ─── Order Items ──────────────────────────────────────────────────────────────
ORDER_ITEMS_SCHEMA = StructType(
    [
        StructField("id", LongType(), nullable=False),
        StructField("order_id", LongType(), nullable=False),
        StructField("user_id", LongType(), nullable=False),
        StructField("days_since_prior_order", DoubleType(), nullable=True),
        StructField("product_id", LongType(), nullable=False),
        StructField("add_to_cart_order", IntegerType(), nullable=False),
        StructField("reordered", IntegerType(), nullable=False),
        StructField("order_timestamp", TimestampType(), nullable=True),
        StructField("date", DateType(), nullable=True),
        StructField("order_month", StringType(), nullable=False),
    ]
)

# ─── Dataset registry ─────────────────────────────────────────────────────────
DATASET_CONFIG: dict[str, dict] = {
    "products": {
        "schema": PRODUCTS_SCHEMA,
        "pk": "product_id",
        "partition_by": None,
        "zorder_cols": [],
        "source_format": "csv",
    },
    "orders": {
        "schema": ORDERS_SCHEMA,
        "pk": "order_id",
        "partition_by": "order_month",
        "zorder_cols": ["order_id"],
        "source_format": "xlsx",
    },
    "order_items": {
        "schema": ORDER_ITEMS_SCHEMA,
        "pk": "id",
        "partition_by": "order_month",
        "zorder_cols": ["order_id", "product_id"],
        "source_format": "xlsx",
    },
}
