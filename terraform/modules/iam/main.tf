data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  catalog_db = "lakehouse_dwh"
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Role 1: Glue execution role                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

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

resource "aws_iam_role_policy" "glue" {
  name   = "glue-execution-policy"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue.json
}

data "aws_iam_policy_document" "glue" {
  # S3 — list bucket for all zones
  statement {
    sid       = "GlueS3List"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "lakehouse-dwh/*", "quarantine/*", "scripts/*", "archive/*", "temp/*"]
    }
  }

  # S3 — read-only (raw source files + scripts)
  statement {
    sid     = "GlueS3ReadOnly"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${var.bucket}/raw/*",
      "arn:aws:s3:::${var.bucket}/scripts/*",
    ]
  }

  # S3 — read-write-delete (Delta tables, quarantine, archive, raw delete for archive job)
  # Wildcards omit the trailing slash to also cover Hadoop _$folder$ directory-marker
  # objects (e.g. lakehouse-dwh_$folder$) that Spark writes on first table creation.
  statement {
    sid     = "GlueS3ReadWriteDelete"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${var.bucket}/lakehouse-dwh*",
      "arn:aws:s3:::${var.bucket}/quarantine*",
      "arn:aws:s3:::${var.bucket}/archive*",
      "arn:aws:s3:::${var.bucket}/raw*",
      "arn:aws:s3:::${var.bucket}/temp*",
    ]
  }

  # Glue Data Catalog — read and write partition metadata
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
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/${local.catalog_db}",
      "arn:aws:glue:${local.region}:${local.account_id}:table/${local.catalog_db}/*",
    ]
  }

  # CloudWatch Logs — continuous logging
  statement {
    sid     = "GlueCloudWatchCreateGroup"
    actions = ["logs:CreateLogGroup"]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/jobs/*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/crawlers",
    ]
  }

  statement {
    sid     = "GlueCloudWatchWrite"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/jobs/${var.project}-*:*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/crawlers:*",
    ]
  }

  # CloudWatch describe (read-only, AWS requires *)
  statement {
    sid       = "GlueCloudWatchDescribe"
    actions   = ["logs:DescribeLogGroups", "logs:DescribeLogStreams"]
    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards — AWS limitation
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Role 2: Step Functions execution role                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "aws_iam_role" "sfn" {
  name = "${var.project}-sfn-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.${local.region}.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sfn" {
  name   = "sfn-execution-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

data "aws_iam_policy_document" "sfn" {
  # Glue job invocation + polling
  statement {
    sid     = "SfnGlueJobs"
    actions = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = [
      var.glue_ingest_job_arn,
      var.glue_archive_job_arn,
    ]
  }

  # Glue crawler management
  statement {
    sid       = "SfnGlueCrawler"
    actions   = ["glue:StartCrawler", "glue:GetCrawler"]
    resources = [var.crawler_arn]
  }

  # Athena query execution
  statement {
    sid       = "SfnAthena"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"]
    resources = [var.athena_workgroup_arn]
  }

  # Glue Data Catalog — Athena resolves table names via the SFN role credentials
  statement {
    sid     = "SfnGlueCatalog"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartition", "glue:GetPartitions"]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/${local.catalog_db}",
      "arn:aws:glue:${local.region}:${local.account_id}:table/${local.catalog_db}/*",
    ]
  }

  # S3 for Athena results
  statement {
    sid       = "SfnAthenaS3"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["arn:aws:s3:::${var.bucket}/athena-results/*"]
  }

  statement {
    sid       = "SfnAthenaS3Location"
    actions   = ["s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::${var.bucket}"]
  }

  # SNS publish for failure alerts
  statement {
    sid       = "SfnSns"
    actions   = ["sns:Publish"]
    resources = [var.sns_topic_arn]
  }

  # CloudWatch Logs delivery (required by Step Functions; AWS mandates *)
  statement {
    sid = "SfnCloudWatchLogs"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards — AWS-mandated for SFN log delivery
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Role 3: EventBridge execution role                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "aws_iam_role" "eventbridge" {
  name = "${var.project}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge" {
  name   = "eventbridge-sfn-policy"
  role   = aws_iam_role.eventbridge.id
  policy = data.aws_iam_policy_document.eventbridge.json
}

data "aws_iam_policy_document" "eventbridge" {
  statement {
    sid       = "EventBridgeStartExecution"
    actions   = ["states:StartExecution"]
    resources = [var.state_machine_arn]
  }
}
