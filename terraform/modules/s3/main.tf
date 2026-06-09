# ─── Bucket ────────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "lakehouse" {
  bucket = var.bucket

  tags = {
    Project = var.project
  }
}

# SSE-S3 encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: quarantine (90-day expiry) + archive (Glacier after 1 year)
resource "aws_s3_bucket_lifecycle_configuration" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  rule {
    id     = "quarantine-expiry"
    status = "Enabled"

    filter {
      prefix = "quarantine/"
    }

    expiration {
      days = 90
    }
  }

  rule {
    id     = "archive-glacier"
    status = "Enabled"

    filter {
      prefix = "archive/"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# ─── Sample data uploads ───────────────────────────────────────────────────────
resource "aws_s3_object" "products_csv" {
  bucket = aws_s3_bucket.lakehouse.id
  key    = "raw/products/products.csv"
  source = "${path.module}/../../../data/products.csv"
  etag   = filemd5("${path.module}/../../../data/products.csv")
}

resource "aws_s3_object" "orders_xlsx" {
  bucket = aws_s3_bucket.lakehouse.id
  key    = "raw/orders/orders_apr_2025.xlsx"
  source = "${path.module}/../../../data/orders_apr_2025.xlsx"
  etag   = filemd5("${path.module}/../../../data/orders_apr_2025.xlsx")
}

resource "aws_s3_object" "order_items_xlsx" {
  bucket = aws_s3_bucket.lakehouse.id
  key    = "raw/order_items/order_items_apr_2025.xlsx"
  source = "${path.module}/../../../data/order_items_apr_2025.xlsx"
  etag   = filemd5("${path.module}/../../../data/order_items_apr_2025.xlsx")
}

# ─── Placeholder for utils.zip ─────────────────────────────────────────────────
# Content is managed by the CD pipeline (`make build-utils-zip && aws s3 cp`).
# Terraform manages the key only; ignore content changes.
resource "aws_s3_object" "utils_zip" {
  bucket  = aws_s3_bucket.lakehouse.id
  key     = "scripts/utils.zip"
  content = "placeholder"

  lifecycle {
    ignore_changes = [content, etag, source]
  }
}
