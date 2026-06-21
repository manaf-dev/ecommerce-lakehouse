data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
}

resource "aws_iam_role" "glue" {
  name = "${var.project}-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue" {
  name   = "glue-execution-policy"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue.json
}

data "aws_iam_policy_document" "glue" {
  statement {
    sid       = "GlueS3List"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "raw/*",
        "lakehouse-dwh/*",
        "quarantine/*",
        "${var.scripts_prefix}*",
        "archived/*",
        "temp/*",
      ]
    }
  }

  statement {
    sid     = "GlueS3ReadOnly"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${var.bucket}/raw/*",
      "arn:aws:s3:::${var.bucket}/${var.scripts_prefix}*",
    ]
  }

  statement {
    sid     = "GlueS3ReadWriteDelete"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${var.bucket}/lakehouse-dwh/*",
      "arn:aws:s3:::${var.bucket}/quarantine/*",
      "arn:aws:s3:::${var.bucket}/archived/*",
      "arn:aws:s3:::${var.bucket}/raw/*",
      "arn:aws:s3:::${var.bucket}/temp/*",
    ]
  }

  statement {
    sid = "GlueCatalog"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:UpdatePartition",
      "glue:DeleteTable",
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/${var.catalog_db}",
      "arn:aws:glue:${local.region}:${local.account_id}:table/${var.catalog_db}/*",
    ]
  }

  statement {
    sid       = "GlueCloudWatchCreateGroup"
    actions   = ["logs:CreateLogGroup"]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/jobs/*"]
  }

  statement {
    sid     = "GlueCloudWatchWrite"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/jobs/${var.project}-*:*",
    ]
  }

  statement {
    sid       = "GlueCloudWatchDescribe"
    actions   = ["logs:DescribeLogGroups", "logs:DescribeLogStreams"]
    resources = ["*"]
  }
}
