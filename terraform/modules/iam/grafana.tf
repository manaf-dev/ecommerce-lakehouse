# ── Grafana read-only IAM user ────────────────────────────────────────────────
# Grants Grafana Cloud the minimum permissions required to run Athena queries
# against the lakehouse views and read Delta table data from S3.
# Access keys are NOT created here — generate them manually after apply:
#   aws iam create-access-key --user-name <name>
resource "aws_iam_user" "grafana_reader" {
  name = "${var.project}-grafana-reader"
  path = "/"
}

resource "aws_iam_user_policy" "grafana_reader" {
  name = "grafana-athena-readonly"
  user = aws_iam_user.grafana_reader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AthenaQueryAccess"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StopQueryExecution",
          "athena:GetWorkGroup",
        ]
        Resource = [
          "arn:aws:athena:${local.region}:${local.account_id}:workgroup/${var.project}-workgroup"
        ]
      },
      {
        Sid    = "GlueCatalogRead"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
        ]
        Resource = [
          "arn:aws:glue:${local.region}:${local.account_id}:catalog",
          "arn:aws:glue:${local.region}:${local.account_id}:database/${var.catalog_db}",
          "arn:aws:glue:${local.region}:${local.account_id}:table/${var.catalog_db}/*",
        ]
      },
      {
        Sid    = "S3LakehouseRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [
          "arn:aws:s3:::${var.bucket}",
          "arn:aws:s3:::${var.bucket}/lakehouse-dwh/*",
        ]
      },
      {
        Sid    = "S3AthenaResultsReadWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.bucket}",
          "arn:aws:s3:::${var.bucket}/athena-results/*",
        ]
      }
    ]
  })
}
