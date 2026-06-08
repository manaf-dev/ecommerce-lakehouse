resource "aws_athena_workgroup" "lakehouse" {
  name  = "${var.project}-workgroup"
  state = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${var.bucket}/athena-results/"
    }
  }
}
