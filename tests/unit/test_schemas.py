"""Unit tests for src/utils/schemas.py — field names, types, nullable flags."""

from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    TimestampType,
)

from utils.schemas import DATASET_CONFIG, ORDER_ITEMS_SCHEMA, ORDERS_SCHEMA, PRODUCTS_SCHEMA


class TestProductsSchema:
    def _field(self, name: str):
        return next(f for f in PRODUCTS_SCHEMA.fields if f.name == name)

    def test_product_id_type_and_nullable(self):
        f = self._field("product_id")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is False

    def test_department_id_type_and_nullable(self):
        f = self._field("department_id")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is False

    def test_department_type_and_nullable(self):
        f = self._field("department")
        assert isinstance(f.dataType, StringType)
        assert f.nullable is False

    def test_product_name_type_and_nullable(self):
        f = self._field("product_name")
        assert isinstance(f.dataType, StringType)
        assert f.nullable is False

    def test_field_count(self):
        assert len(PRODUCTS_SCHEMA.fields) == 4


class TestOrdersSchema:
    def _field(self, name: str):
        return next(f for f in ORDERS_SCHEMA.fields if f.name == name)

    def test_order_month_is_string(self):
        f = self._field("order_month")
        assert isinstance(f.dataType, StringType)
        assert f.nullable is False

    def test_order_id_is_long_not_nullable(self):
        f = self._field("order_id")
        assert isinstance(f.dataType, LongType)
        assert f.nullable is False

    def test_order_num_is_nullable(self):
        f = self._field("order_num")
        assert isinstance(f.dataType, LongType)
        assert f.nullable is True

    def test_order_timestamp_is_timestamp(self):
        f = self._field("order_timestamp")
        assert isinstance(f.dataType, TimestampType)

    def test_total_amount_is_double(self):
        f = self._field("total_amount")
        assert isinstance(f.dataType, DoubleType)

    def test_date_is_date_type(self):
        f = self._field("date")
        assert isinstance(f.dataType, DateType)


class TestOrderItemsSchema:
    def _field(self, name: str):
        return next(f for f in ORDER_ITEMS_SCHEMA.fields if f.name == name)

    def test_days_since_prior_order_is_double_nullable(self):
        f = self._field("days_since_prior_order")
        assert isinstance(f.dataType, DoubleType)
        assert f.nullable is True

    def test_order_timestamp_is_nullable(self):
        f = self._field("order_timestamp")
        assert isinstance(f.dataType, TimestampType)
        assert f.nullable is True

    def test_id_is_long_not_nullable(self):
        f = self._field("id")
        assert isinstance(f.dataType, LongType)
        assert f.nullable is False

    def test_add_to_cart_order_is_integer(self):
        f = self._field("add_to_cart_order")
        assert isinstance(f.dataType, IntegerType)

    def test_reordered_is_integer(self):
        f = self._field("reordered")
        assert isinstance(f.dataType, IntegerType)


class TestDatasetConfig:
    def test_keys(self):
        assert set(DATASET_CONFIG.keys()) == {"products", "orders", "order_items"}

    def test_products_pk(self):
        assert DATASET_CONFIG["products"]["pk"] == "product_id"

    def test_products_no_partition(self):
        assert DATASET_CONFIG["products"]["partition_by"] is None

    def test_products_no_zorder(self):
        assert DATASET_CONFIG["products"]["zorder_cols"] == []

    def test_products_source_format_csv(self):
        assert DATASET_CONFIG["products"]["source_format"] == "csv"

    def test_orders_partition_by(self):
        assert DATASET_CONFIG["orders"]["partition_by"] == "order_month"

    def test_orders_zorder_cols(self):
        assert DATASET_CONFIG["orders"]["zorder_cols"] == ["order_id"]

    def test_order_items_zorder_cols(self):
        assert DATASET_CONFIG["order_items"]["zorder_cols"] == ["order_id", "product_id"]

    def test_order_items_pk(self):
        assert DATASET_CONFIG["order_items"]["pk"] == "id"

    def test_order_items_source_format_xlsx(self):
        assert DATASET_CONFIG["order_items"]["source_format"] == "xlsx"
