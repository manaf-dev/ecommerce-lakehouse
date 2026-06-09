"""Unit tests for src/utils/readers.py."""

import pandas as pd
import pytest
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from utils.readers import read_csv_to_spark, read_dataset, read_xlsx_to_spark
from utils.schemas import PRODUCTS_SCHEMA

# Minimal schema for XLSX reader tests (avoids Timestamp/Date complexity)
_SIMPLE_SCHEMA = StructType(
    [
        StructField("id", IntegerType(), nullable=True),
        StructField("name", StringType(), nullable=True),
    ]
)


class TestReadCsvToSpark:
    def test_read_csv_products_row_count(self, spark, tmp_path):
        """CSV with 3 data rows returns 3-row DataFrame."""
        csv_file = tmp_path / "products.csv"
        csv_file.write_text(
            "product_id,department_id,department,product_name\n"
            "1,1,Beverages,Cola\n"
            "2,1,Beverages,Water\n"
            "3,2,Snacks,Chips\n"
        )
        df = read_csv_to_spark(spark, str(csv_file), PRODUCTS_SCHEMA)
        assert df.count() == 3

    def test_read_csv_products_schema_matches(self, spark, tmp_path):
        """CSV reader enforces the given schema on the result."""
        csv_file = tmp_path / "p.csv"
        csv_file.write_text("product_id,department_id,department,product_name\n1,1,Dept,Product\n")
        df = read_csv_to_spark(spark, str(csv_file), PRODUCTS_SCHEMA)
        field_names = [f.name for f in df.schema.fields]
        assert field_names == ["product_id", "department_id", "department", "product_name"]

    def test_read_dataset_dispatches_csv(self, spark, tmp_path):
        """read_dataset('csv') delegates to read_csv_to_spark."""
        csv_file = tmp_path / "p.csv"
        csv_file.write_text("product_id,department_id,department,product_name\n10,5,HPC,Soap\n")
        df = read_dataset(spark, str(csv_file), "csv", PRODUCTS_SCHEMA)
        assert df.count() == 1


class TestReadXlsxToSpark:
    def test_read_xlsx_single_sheet(self, spark, tmp_path):
        """Single-sheet XLSX with 5 rows returns 5 rows."""
        xlsx_path = tmp_path / "data.xlsx"
        pd.DataFrame({"id": list(range(1, 6)), "name": [f"n{i}" for i in range(1, 6)]}).to_excel(
            str(xlsx_path), sheet_name="Sheet1", index=False
        )

        df = read_xlsx_to_spark(spark, str(xlsx_path), _SIMPLE_SCHEMA)
        assert df.count() == 5

    def test_read_xlsx_multi_sheet(self, spark, tmp_path):
        """CRITICAL: Two sheets × 5 rows each → 10 rows total."""
        xlsx_path = tmp_path / "multi.xlsx"
        with pd.ExcelWriter(str(xlsx_path)) as writer:
            pd.DataFrame(
                {"id": list(range(1, 6)), "name": [f"a{i}" for i in range(1, 6)]}
            ).to_excel(writer, sheet_name="Sheet1", index=False)
            pd.DataFrame(
                {"id": list(range(6, 11)), "name": [f"b{i}" for i in range(6, 11)]}
            ).to_excel(writer, sheet_name="Sheet2", index=False)

        df = read_xlsx_to_spark(spark, str(xlsx_path), _SIMPLE_SCHEMA)
        assert df.count() == 10

    def test_read_xlsx_empty_sheet(self, spark, tmp_path):
        """XLSX with one empty sheet returns 0 rows without raising."""
        xlsx_path = tmp_path / "empty.xlsx"
        # Write header only — no data rows
        pd.DataFrame(columns=["id", "name"]).to_excel(
            str(xlsx_path), sheet_name="EmptySheet", index=False
        )
        df = read_xlsx_to_spark(spark, str(xlsx_path), _SIMPLE_SCHEMA)
        assert df.count() == 0

    def test_read_xlsx_multi_sheet_one_empty(self, spark, tmp_path):
        """Multi-sheet: one populated + one empty → only populated rows returned."""
        xlsx_path = tmp_path / "partial.xlsx"
        with pd.ExcelWriter(str(xlsx_path)) as writer:
            pd.DataFrame({"id": [1, 2], "name": ["x", "y"]}).to_excel(
                writer, sheet_name="Data", index=False
            )
            pd.DataFrame(columns=["id", "name"]).to_excel(writer, sheet_name="Empty", index=False)
        df = read_xlsx_to_spark(spark, str(xlsx_path), _SIMPLE_SCHEMA)
        assert df.count() == 2

    def test_read_dataset_dispatches_xlsx(self, spark, tmp_path):
        """read_dataset('xlsx') delegates to read_xlsx_to_spark."""
        xlsx_path = tmp_path / "d.xlsx"
        pd.DataFrame({"id": [99], "name": ["test"]}).to_excel(
            str(xlsx_path), sheet_name="S", index=False
        )
        df = read_dataset(spark, str(xlsx_path), "xlsx", _SIMPLE_SCHEMA)
        assert df.count() == 1

    def test_read_dataset_unknown_format_raises(self, spark, tmp_path):
        """read_dataset raises ValueError for unknown format."""
        with pytest.raises(ValueError, match="Unsupported source_format"):
            read_dataset(spark, "/fake/path", "parquet", _SIMPLE_SCHEMA)
