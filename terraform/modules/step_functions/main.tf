# ─── SNS topic + subscription ─────────────────────────────────────────────────
resource "aws_sns_topic" "pipeline_alerts" {
  name = "${var.project}-pipeline-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.pipeline_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ─── CloudWatch log group for Step Functions ──────────────────────────────────
resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/states/${var.project}-pipeline"
  retention_in_days = 30
}

# ─── Step Functions state machine ─────────────────────────────────────────────
resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project}-pipeline"
  role_arn = var.sfn_role_arn

  definition = templatefile(
    "${path.module}/../../../src/step_functions/state_machine.asl.json",
    {
      bucket         = var.bucket
      project        = var.project
      workgroup_name = var.workgroup_name
      sns_topic_arn  = aws_sns_topic.pipeline_alerts.arn
      catalog_db     = "lakehouse_dwh"
    }
  )

  logging_configuration {
    level                  = "ERROR"
    include_execution_data = true
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
  }

  depends_on = [aws_cloudwatch_log_group.sfn]
}

# ─── EventBridge rule — S3 ObjectCreated on raw/ prefixes ────────────────────
resource "aws_cloudwatch_event_rule" "s3_trigger" {
  name        = "${var.project}-s3-raw-trigger"
  description = "Trigger lakehouse pipeline when files land in S3 raw/ zone"

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

# ─── EventBridge target → Step Functions ─────────────────────────────────────
resource "aws_cloudwatch_event_target" "sfn" {
  rule     = aws_cloudwatch_event_rule.s3_trigger.name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = var.eventbridge_role_arn

  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
    }

    # The StartIngestion Pass state in the ASL resolves dataset-specific paths
    # from $.bucket and $.key at execution start.
    input_template = <<-EOT
      {
        "bucket": "<bucket>",
        "key": "<key>",
        "order_month": "unknown"
      }
    EOT
  }
}

# ─── Enable EventBridge notifications on the S3 bucket ────────────────────────
resource "aws_s3_bucket_notification" "eventbridge" {
  bucket      = var.bucket
  eventbridge = true
}
