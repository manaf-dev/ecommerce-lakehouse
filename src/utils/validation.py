"""Data quality validation functions.

Each function accepts a source DataFrame (and optional reference tables for
referential checks) and returns ``(valid_df, rejected_df)``.

The rejected DataFrame gains a ``_rejection_reason`` column that contains a
comma-separated string of every failed rule name for that row.

Rejection reason strings are canonical — match them exactly in tests and
quarantine queries:
  products    : "product_id null or <= 0", "department_id null or <= 0",
                "department null or empty", "product_name null or empty"
  orders      : "order_id null or <= 0", "user_id null or <= 0",
                "order_timestamp invalid or year < 2020",
                "total_amount not > 0",
                "date does not match order_timestamp date"
  order_items : "id null or <= 0", "add_to_cart_order < 1",
                "reordered not in {0,1}", "days_since_prior_order < 0",
                "order_id not found in orders",
                "product_id not found in products",
                "user_id mismatch for order_id"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql import functions as F

if TYPE_CHECKING:
    from pyspark.sql import DataFrame  # pragma: no cover


def _split_valid_rejected(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Split df on the _failure_reasons array column.

    Returns:
        (valid_df, rejected_df) where rejected_df has a ``_rejection_reason``
        string column instead of the intermediate ``_failure_reasons`` array.
    """
    valid_df = df.filter(F.size("_failure_reasons") == 0).drop("_failure_reasons")
    rejected_df = (
        df.filter(F.size("_failure_reasons") > 0)
        .withColumn("_rejection_reason", F.array_join(F.col("_failure_reasons"), ", "))
        .drop("_failure_reasons")
    )
    return valid_df, rejected_df


def validate_products(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Validate the products dataset.

    Rules applied (ordered, all checked simultaneously):
      1. product_id > 0 and NOT NULL
      2. department_id > 0 and NOT NULL
      3. department NOT NULL and not blank
      4. product_name NOT NULL and not blank

    Args:
        df: Raw products DataFrame.

    Returns:
        Tuple of (valid_df, rejected_df).
    """
    reasons = F.array(
        F.when(
            F.col("product_id").isNull() | (F.col("product_id") <= 0),
            F.lit("product_id null or <= 0"),
        ),
        F.when(
            F.col("department_id").isNull() | (F.col("department_id") <= 0),
            F.lit("department_id null or <= 0"),
        ),
        F.when(
            F.col("department").isNull() | (F.trim(F.col("department")) == ""),
            F.lit("department null or empty"),
        ),
        F.when(
            F.col("product_name").isNull() | (F.trim(F.col("product_name")) == ""),
            F.lit("product_name null or empty"),
        ),
    )
    df = df.withColumn("_failure_reasons", F.filter(reasons, lambda x: x.isNotNull()))
    return _split_valid_rejected(df)


def validate_orders(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Validate the orders dataset.

    Rules applied (all checked simultaneously):
      1. order_id > 0 and NOT NULL
      2. user_id > 0 and NOT NULL
      3. order_timestamp NOT NULL and year >= 2020
      4. total_amount > 0 (catches null and non-positive values)
      5. date NOT NULL and equals cast(order_timestamp as date)

    Args:
        df: Raw orders DataFrame.

    Returns:
        Tuple of (valid_df, rejected_df).
    """
    reasons = F.array(
        F.when(
            F.col("order_id").isNull() | (F.col("order_id") <= 0),
            F.lit("order_id null or <= 0"),
        ),
        F.when(
            F.col("user_id").isNull() | (F.col("user_id") <= 0),
            F.lit("user_id null or <= 0"),
        ),
        F.when(
            F.col("order_timestamp").isNull() | (F.year(F.col("order_timestamp")) < 2020),
            F.lit("order_timestamp invalid or year < 2020"),
        ),
        F.when(
            F.col("total_amount").isNull() | (F.col("total_amount") <= 0),
            F.lit("total_amount not > 0"),
        ),
        F.when(
            F.col("date").isNull()
            | (
                F.col("order_timestamp").isNotNull()
                & (F.col("date") != F.to_date(F.col("order_timestamp")))
            ),
            F.lit("date does not match order_timestamp date"),
        ),
    )
    df = df.withColumn("_failure_reasons", F.filter(reasons, lambda x: x.isNotNull()))
    return _split_valid_rejected(df)


def validate_order_items(
    df: DataFrame,
    orders_delta: DataFrame,
    products_delta: DataFrame,
) -> tuple[DataFrame, DataFrame]:
    """Validate the order_items dataset with referential integrity checks.

    Rules applied in order (simple checks first, then referential):
      1. id > 0 and NOT NULL
      2. add_to_cart_order >= 1
      3. reordered IN (0, 1)
      4. days_since_prior_order IS NULL OR >= 0  (null is valid for first orders)
      5. order_id EXISTS IN orders_delta
      6. product_id EXISTS IN products_delta
      7. user_id matches orders_delta.user_id for the same order_id

    Args:
        df: Raw order_items DataFrame.
        orders_delta: Committed orders Delta table (used for ref checks).
        products_delta: Committed products Delta table (used for ref checks).

    Returns:
        Tuple of (valid_df, rejected_df).
    """
    # ── Step 1: Simple column checks ──────────────────────────────────────────
    simple_reasons = F.array(
        F.when(
            F.col("id").isNull() | (F.col("id") <= 0),
            F.lit("id null or <= 0"),
        ),
        F.when(
            F.col("add_to_cart_order").isNull() | (F.col("add_to_cart_order") < 1),
            F.lit("add_to_cart_order < 1"),
        ),
        F.when(
            F.col("reordered").isNull() | (~F.col("reordered").isin(0, 1)),
            F.lit("reordered not in {0,1}"),
        ),
        F.when(
            F.col("days_since_prior_order").isNotNull() & (F.col("days_since_prior_order") < 0),
            F.lit("days_since_prior_order < 0"),
        ),
    )
    df = df.withColumn("_failure_reasons", F.filter(simple_reasons, lambda x: x.isNotNull()))

    # ── Step 2: order_id referential check (LEFT ANTI join pattern) ───────────
    valid_order_ids = orders_delta.select(F.col("order_id").alias("_valid_order_id")).distinct()
    df = (
        df.join(valid_order_ids, df["order_id"] == valid_order_ids["_valid_order_id"], "left")
        .withColumn(
            "_failure_reasons",
            F.when(
                F.col("_valid_order_id").isNull(),
                F.array_append(F.col("_failure_reasons"), F.lit("order_id not found in orders")),
            ).otherwise(F.col("_failure_reasons")),
        )
        .drop("_valid_order_id")
    )

    # ── Step 3: product_id referential check ─────────────────────────────────
    valid_product_ids = products_delta.select(
        F.col("product_id").alias("_valid_product_id")
    ).distinct()
    df = (
        df.join(
            valid_product_ids,
            df["product_id"] == valid_product_ids["_valid_product_id"],
            "left",
        )
        .withColumn(
            "_failure_reasons",
            F.when(
                F.col("_valid_product_id").isNull(),
                F.array_append(
                    F.col("_failure_reasons"), F.lit("product_id not found in products")
                ),
            ).otherwise(F.col("_failure_reasons")),
        )
        .drop("_valid_product_id")
    )

    # ── Step 4: user_id mismatch check ───────────────────────────────────────
    # Only triggered when order_id IS found in orders but user_id differs.
    order_user_lookup = orders_delta.select(
        F.col("order_id").alias("_ref_order_id"),
        F.col("user_id").alias("_ref_user_id"),
    ).distinct()
    df = (
        df.join(
            order_user_lookup,
            df["order_id"] == order_user_lookup["_ref_order_id"],
            "left",
        )
        .withColumn(
            "_failure_reasons",
            F.when(
                F.col("_ref_order_id").isNotNull() & (F.col("user_id") != F.col("_ref_user_id")),
                F.array_append(F.col("_failure_reasons"), F.lit("user_id mismatch for order_id")),
            ).otherwise(F.col("_failure_reasons")),
        )
        .drop("_ref_order_id", "_ref_user_id")
    )

    return _split_valid_rejected(df)
