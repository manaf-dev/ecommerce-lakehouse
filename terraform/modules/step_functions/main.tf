data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "archive_file" "start_pipeline" {
  type        = "zip"
  source_file = "${path.module}/../../../src/lambda_functions/start_pipeline.py"
  output_path = "${path.module}/start_pipeline.zip"
}

data "archive_file" "archive_files" {
  type        = "zip"
  source_file = "${path.module}/../../../src/lambda_functions/archive_files.py"
  output_path = "${path.module}/archive_files.zip"
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
}

# ─── SNS ───────────────────────────────────────────────────────────────────────
resource "aws_sns_topic" "pipeline_alerts" {
  name = "${var.project}-pipeline-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.pipeline_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ─── CloudWatch log groups ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/states/${var.project}-pipeline"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "start_pipeline" {
  name              = "/aws/lambda/${var.project}-start-pipeline"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "archive_files" {
  name              = "/aws/lambda/${var.project}-archive-files"
  retention_in_days = 14
}

# ─── Step Functions execution role ─────────────────────────────────────────────
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
  statement {
    sid     = "SfnGlueJobs"
    actions = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = [var.glue_ingest_job_arn]
  }

  statement {
    sid = "SfnAthena"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
    ]
    resources = ["arn:aws:athena:${local.region}:${local.account_id}:workgroup/${var.workgroup_name}"]
  }

  statement {
    sid       = "SfnAthenaS3"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      "arn:aws:s3:::${var.bucket}",
      "arn:aws:s3:::${var.bucket}/athena-results/*",
    ]
  }

  statement {
    sid = "SfnGlueCatalogRead"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/${var.catalog_db_name}",
      "arn:aws:glue:${local.region}:${local.account_id}:table/${var.catalog_db_name}/*",
    ]
  }

  statement {
    sid       = "SfnInvokeArchiveLambda"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.archive_files.arn]
  }

  statement {
    sid       = "SfnSns"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.pipeline_alerts.arn]
  }

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
    resources = ["*"]
  }
}

# ─── State machine (Standard workflow) ─────────────────────────────────────────
resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project}-pipeline"
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile(
    "${path.module}/../../../src/step_functions/state_machine.asl.json",
    {
      project              = var.project
      catalog_db_name      = var.catalog_db_name
      workgroup_name       = var.workgroup_name
      sns_topic_arn        = aws_sns_topic.pipeline_alerts.arn
      archive_lambda_name  = aws_lambda_function.archive_files.function_name
    }
  )

  logging_configuration {
    level                  = "ERROR"
    include_execution_data = true
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
  }

  depends_on = [aws_cloudwatch_log_group.sfn, aws_lambda_function.archive_files]
}

# ─── SQS debounce queue ────────────────────────────────────────────────────────
resource "aws_sqs_queue" "pipeline" {
  name                       = "${var.project}-pipeline-queue"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20
}

# ─── Lambda: start pipeline (concurrency = 1) ────────────────────────────────────
resource "aws_iam_role" "start_pipeline" {
  name = "${var.project}-start-pipeline-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "start_pipeline" {
  name   = "start-pipeline-policy"
  role   = aws_iam_role.start_pipeline.id
  policy = data.aws_iam_policy_document.start_pipeline.json
}

data "aws_iam_policy_document" "start_pipeline" {
  statement {
    sid = "StartPipelineSfn"
    actions = [
      "states:StartExecution",
      "states:ListExecutions",
    ]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }

  statement {
    sid = "StartPipelineLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.project}-*:*"]
  }

  statement {
    sid = "StartPipelineSqs"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.pipeline.arn]
  }
}

resource "aws_lambda_function" "start_pipeline" {
  function_name = "${var.project}-start-pipeline"
  role          = aws_iam_role.start_pipeline.arn
  handler       = "start_pipeline.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 128

  filename         = data.archive_file.start_pipeline.output_path
  source_code_hash = data.archive_file.start_pipeline.output_base64sha256

  reserved_concurrent_executions = 1

  environment {
    variables = {
      STATE_MACHINE_ARN = aws_sfn_state_machine.pipeline.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.start_pipeline]
}

resource "aws_lambda_event_source_mapping" "start_pipeline" {
  event_source_arn = aws_sqs_queue.pipeline.arn
  function_name    = aws_lambda_function.start_pipeline.arn
  batch_size       = 10
  maximum_batching_window_in_seconds = 30
}

# ─── Lambda: archive files ─────────────────────────────────────────────────────
resource "aws_iam_role" "archive_files" {
  name = "${var.project}-archive-files-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "archive_files" {
  name   = "archive-files-policy"
  role   = aws_iam_role.archive_files.id
  policy = data.aws_iam_policy_document.archive_files.json
}

data "aws_iam_policy_document" "archive_files" {
  statement {
    sid = "ArchiveFilesLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.project}-*:*"]
  }

  statement {
    sid     = "ArchiveFilesS3List"
    actions = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "archived/*"]
    }
  }

  statement {
    sid     = "ArchiveFilesS3Objects"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${var.bucket}/raw/*",
      "arn:aws:s3:::${var.bucket}/archived/*",
    ]
  }
}

resource "aws_lambda_function" "archive_files" {
  function_name = "${var.project}-archive-files"
  role          = aws_iam_role.archive_files.arn
  handler       = "archive_files.handler"
  runtime       = "python3.12"
  timeout       = 120
  memory_size   = 128

  filename         = data.archive_file.archive_files.output_path
  source_code_hash = data.archive_file.archive_files.output_base64sha256

  depends_on = [aws_cloudwatch_log_group.archive_files]
}

# ─── EventBridge → SQS (debounced trigger) ─────────────────────────────────────
resource "aws_cloudwatch_event_rule" "s3_trigger" {
  name        = "${var.project}-s3-raw-trigger"
  description = "Route S3 raw-zone uploads to the pipeline debounce queue"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    resources   = ["arn:aws:s3:::${var.bucket}"]
    detail = {
      object = {
        key = [
          { prefix = "raw/products/" },
          { prefix = "raw/orders/" },
          { prefix = "raw/order_items/" },
        ]
      }
    }
  })
}

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
  name   = "eventbridge-sqs-policy"
  role   = aws_iam_role.eventbridge.id
  policy = data.aws_iam_policy_document.eventbridge.json
}

data "aws_iam_policy_document" "eventbridge" {
  statement {
    sid       = "EventBridgeSendToSqs"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.pipeline.arn]
  }
}

resource "aws_cloudwatch_event_target" "sqs" {
  rule      = aws_cloudwatch_event_rule.s3_trigger.name
  target_id = "pipeline-queue"
  arn       = aws_sqs_queue.pipeline.arn
  role_arn  = aws_iam_role.eventbridge.arn
}

resource "aws_sqs_queue_policy" "pipeline" {
  queue_url = aws_sqs_queue.pipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowEventBridgeSend"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.pipeline.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.s3_trigger.arn
          }
        }
      },
    ]
  })
}

resource "aws_s3_bucket_notification" "eventbridge" {
  bucket      = var.bucket
  eventbridge = true
}
