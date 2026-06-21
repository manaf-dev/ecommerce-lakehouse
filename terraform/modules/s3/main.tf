# ─── Bucket ────────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "lakehouse" {
  bucket = var.bucket

  tags = {
    Project = var.project
  }
}

resource "aws_s3_bucket_versioning" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tls_only" {
  bucket = aws_s3_bucket.lakehouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.lakehouse.arn,
        "${aws_s3_bucket.lakehouse.arn}/*",
      ]
      Condition = {
        Bool = {
          "aws:SecureTransport" = "false"
        }
      }
    }]
  })
}

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
    id     = "archived-glacier"
    status = "Enabled"

    filter {
      prefix = "archived/"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# Placeholder for utils.zip — content is uploaded by CI/CD before terraform apply.
resource "aws_s3_object" "utils_zip" {
  bucket  = aws_s3_bucket.lakehouse.id
  key     = "scripts/utils.zip"
  content = "placeholder"

  lifecycle {
    ignore_changes = [content, etag, source]
  }
}
