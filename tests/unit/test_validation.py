"""Unit tests for src/utils/validation.py.

Covers all 16 individual validation rules plus multi-rule failures and
boundary conditions.  Each rule class names the rule being exercised.
"""

from datetime import date, datetime

from pyspark.sql.types import StructField, StructType

from utils.schemas import ORDER_ITEMS_SCHEMA, ORDERS_SCHEMA, PRODUCTS_SCHEMA
from utils.validation import validate_order_items, validate_orders, validate_products

# ─── Helpers ──────────────────────────────────────────────────────────────────

_VALID_PRODUCT = (1, 1, "Beverages", "Cola")
_VALID_ORDER = (1, None, 1, datetime(2025, 4, 1, 10, 0), 100.0, date(2025, 4, 1), "2025-04")
# user_id=10 must match the orders fixture (order_id=1 → user_id=10)
_VALID_ORDER_ITEM = (1, 1, 10, None, 1, 1, 0, None, None, "2025-04")


def _all_nullable(schema: StructType) -> StructType:
    """Return a copy of schema with every field nullable=True.

    Required because PySpark 3.5 enforces non-nullable at createDataFrame time,
    but validation tests need to inject None into PK columns to exercise null checks.
    """
    return StructType([StructField(f.name, f.dataType, True) for f in schema.fields])


def _products_df(spark, rows):
    return spark.createDataFrame(rows, schema=_all_nullable(PRODUCTS_SCHEMA))


def _orders_df(spark, rows):
    return spark.createDataFrame(rows, schema=_all_nullable(ORDERS_SCHEMA))


def _order_items_df(spark, rows):
    return spark.createDataFrame(rows, schema=_all_nullable(ORDER_ITEMS_SCHEMA))


# ─── Products validation ──────────────────────────────────────────────────────


class TestValidateProducts:
    def test_null_product_id(self, spark):
        row = (None, 1, "Dept", "Product")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        reason = rej.collect()[0]["_rejection_reason"]
        assert "product_id null or <= 0" in reason

    def test_zero_product_id(self, spark):
        row = (0, 1, "Dept", "Product")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "product_id null or <= 0" in rej.collect()[0]["_rejection_reason"]

    def test_null_department_id(self, spark):
        row = (1, None, "Dept", "Product")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "department_id null or <= 0" in rej.collect()[0]["_rejection_reason"]

    def test_zero_department_id(self, spark):
        row = (1, 0, "Dept", "Product")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "department_id null or <= 0" in rej.collect()[0]["_rejection_reason"]

    def test_null_department(self, spark):
        row = (1, 1, None, "Product")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "department null or empty" in rej.collect()[0]["_rejection_reason"]

    def test_empty_department(self, spark):
        row = (1, 1, "  ", "Product")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "department null or empty" in rej.collect()[0]["_rejection_reason"]

    def test_null_product_name(self, spark):
        row = (1, 1, "Dept", None)
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "product_name null or empty" in rej.collect()[0]["_rejection_reason"]

    def test_empty_product_name(self, spark):
        row = (1, 1, "Dept", "")
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        assert rej.count() == 1
        assert "product_name null or empty" in rej.collect()[0]["_rejection_reason"]

    def test_valid_batch_zero_rejections(self, spark):
        rows = [_VALID_PRODUCT, (2, 2, "Snacks", "Chips"), (3, 3, "Dairy", "Milk")]
        valid, rej = validate_products(_products_df(spark, rows))
        assert valid.count() == 3
        assert rej.count() == 0

    def test_multi_rule_rejection(self, spark):
        """A row with two failures gets both reasons comma-separated."""
        row = (None, 0, "Dept", "Product")  # product_id null + department_id zero
        df = _products_df(spark, [row])
        _, rej = validate_products(df)
        reason = rej.collect()[0]["_rejection_reason"]
        assert "product_id null or <= 0" in reason
        assert "department_id null or <= 0" in reason


# ─── Orders validation ────────────────────────────────────────────────────────


class TestValidateOrders:
    def test_null_order_id(self, spark):
        row = (None, None, 1, datetime(2025, 4, 1), 10.0, date(2025, 4, 1), "2025-04")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        assert rej.count() == 1
        assert "order_id null or <= 0" in rej.collect()[0]["_rejection_reason"]

    def test_null_user_id(self, spark):
        row = (1, None, None, datetime(2025, 4, 1), 10.0, date(2025, 4, 1), "2025-04")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        assert rej.count() == 1
        assert "user_id null or <= 0" in rej.collect()[0]["_rejection_reason"]

    def test_order_timestamp_year_2019(self, spark):
        """order_timestamp year < 2020 is invalid."""
        row = (1, None, 1, datetime(2019, 12, 31), 10.0, date(2019, 12, 31), "2019-12")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        assert rej.count() == 1
        assert "order_timestamp invalid or year < 2020" in rej.collect()[0]["_rejection_reason"]

    def test_total_amount_zero(self, spark):
        row = (1, None, 1, datetime(2025, 4, 1), 0.0, date(2025, 4, 1), "2025-04")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        assert rej.count() == 1
        assert "total_amount not > 0" in rej.collect()[0]["_rejection_reason"]

    def test_total_amount_null(self, spark):
        row = (1, None, 1, datetime(2025, 4, 1), None, date(2025, 4, 1), "2025-04")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        assert rej.count() == 1
        assert "total_amount not > 0" in rej.collect()[0]["_rejection_reason"]

    def test_date_mismatch(self, spark):
        """date column that doesn't match order_timestamp date is invalid."""
        row = (1, None, 1, datetime(2025, 4, 1, 10), 10.0, date(2025, 4, 2), "2025-04")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        assert rej.count() == 1
        assert "date does not match order_timestamp date" in rej.collect()[0]["_rejection_reason"]

    def test_valid_orders_zero_rejections(self, spark):
        rows = [
            _VALID_ORDER,
            (2, None, 2, datetime(2025, 4, 2), 50.0, date(2025, 4, 2), "2025-04"),
        ]
        valid, rej = validate_orders(_orders_df(spark, rows))
        assert valid.count() == 2
        assert rej.count() == 0

    def test_multi_rule_failure_row(self, spark):
        """Row with null user_id AND total_amount=0 gets both reasons."""
        row = (1, None, None, datetime(2025, 4, 1), 0.0, date(2025, 4, 1), "2025-04")
        df = _orders_df(spark, [row])
        _, rej = validate_orders(df)
        reason = rej.collect()[0]["_rejection_reason"]
        assert "user_id null or <= 0" in reason
        assert "total_amount not > 0" in reason


# ─── Order items validation ───────────────────────────────────────────────────


class TestValidateOrderItems:
    def _setup(self, spark):
        """Return pre-populated orders and products reference DataFrames."""
        orders = _orders_df(
            spark,
            [(1, None, 10, datetime(2025, 4, 1), 100.0, date(2025, 4, 1), "2025-04")],
        )
        products = _products_df(spark, [(1, 1, "Beverages", "Cola")])
        return orders, products

    def test_null_id(self, spark):
        orders, products = self._setup(spark)
        row = (None, 1, 10, None, 1, 1, 0, None, None, "2025-04")
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "id null or <= 0" in rej.collect()[0]["_rejection_reason"]

    def test_add_to_cart_order_zero(self, spark):
        orders, products = self._setup(spark)
        row = (1, 1, 10, None, 1, 0, 0, None, None, "2025-04")
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "add_to_cart_order < 1" in rej.collect()[0]["_rejection_reason"]

    def test_reordered_value_two(self, spark):
        orders, products = self._setup(spark)
        row = (1, 1, 10, None, 1, 1, 2, None, None, "2025-04")
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "reordered not in {0,1}" in rej.collect()[0]["_rejection_reason"]

    def test_negative_days_since_prior_order(self, spark):
        orders, products = self._setup(spark)
        row = (1, 1, 10, -1.0, 1, 1, 0, None, None, "2025-04")
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "days_since_prior_order < 0" in rej.collect()[0]["_rejection_reason"]

    def test_days_since_prior_null_is_valid(self, spark):
        """Null days_since_prior_order is NOT a rejection — valid for first-ever orders."""
        orders, products = self._setup(spark)
        row = (1, 1, 10, None, 1, 1, 0, None, None, "2025-04")
        df = _order_items_df(spark, [row])
        valid, rej = validate_order_items(df, orders, products)
        assert valid.count() == 1
        assert rej.count() == 0

    def test_order_id_not_in_orders(self, spark):
        """order_id that does not exist in orders → quarantined."""
        orders, products = self._setup(spark)
        row = (1, 999, 10, None, 1, 1, 0, None, None, "2025-04")  # order_id=999 unknown
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "order_id not found in orders" in rej.collect()[0]["_rejection_reason"]

    def test_product_id_not_in_products(self, spark):
        """product_id that does not exist in products → quarantined."""
        orders, products = self._setup(spark)
        row = (1, 1, 10, None, 999, 1, 0, None, None, "2025-04")  # product_id=999 unknown
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "product_id not found in products" in rej.collect()[0]["_rejection_reason"]

    def test_user_id_mismatch(self, spark):
        """user_id mismatch for a known order_id → quarantined."""
        orders, products = self._setup(spark)
        row = (1, 1, 99, None, 1, 1, 0, None, None, "2025-04")  # user_id=99 ≠ order's 10
        df = _order_items_df(spark, [row])
        _, rej = validate_order_items(df, orders, products)
        assert rej.count() == 1
        assert "user_id mismatch for order_id" in rej.collect()[0]["_rejection_reason"]

    def test_valid_order_items_zero_rejections(self, spark):
        orders, products = self._setup(spark)
        # (1, 1, 10, None, 1, 1, 0, None, None, "2025-04") — user_id=10 matches order
        row = _VALID_ORDER_ITEM
        df = _order_items_df(spark, [row])
        valid, rej = validate_order_items(df, orders, products)
        assert valid.count() == 1
        assert rej.count() == 0

    def test_zero_silent_drops(self, spark):
        """Every row lands in exactly one of valid or rejected (no silent drops)."""
        orders, products = self._setup(spark)
        rows = [
            _VALID_ORDER_ITEM,  # valid
            (2, 999, 10, None, 1, 1, 0, None, None, "2025-04"),  # unknown order_id
            (3, 1, 99, None, 1, 1, 0, None, None, "2025-04"),  # user_id mismatch
        ]
        df = _order_items_df(spark, rows)
        valid, rej = validate_order_items(df, orders, products)
        assert valid.count() + rej.count() == len(rows)
