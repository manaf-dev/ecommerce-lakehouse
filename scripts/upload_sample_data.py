import os
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

UPLOADS = {
    "products.csv": "raw/products/products.csv",
    "orders_apr_2025.xlsx": "raw/orders/orders_apr_2025.xlsx",
    "order_items_apr_2025.xlsx": "raw/order_items/order_items_apr_2025.xlsx",
}


def upload_sample_data() -> None:
    bucket = os.environ.get("LAKEHOUSE_BUCKET")
    if not bucket:
        print("Error: LAKEHOUSE_BUCKET env var not set", file=sys.stderr)
        sys.exit(1)

    for filename in UPLOADS:
        local_path = DATA_DIR / filename
        assert local_path.exists(), f"Data file not found: {local_path}"

    s3 = boto3.client("s3")
    for filename, s3_key in UPLOADS.items():
        local_path = DATA_DIR / filename
        print(f"Uploading {local_path} -> s3://{bucket}/{s3_key}")
        s3.upload_file(str(local_path), bucket, s3_key)
        print(f"  Done: {filename}")


if __name__ == "__main__":
    upload_sample_data()
