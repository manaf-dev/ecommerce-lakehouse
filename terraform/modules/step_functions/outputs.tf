output "state_machine_arn" {
  description = "Step Functions pipeline state machine ARN"
  value       = aws_sfn_state_machine.pipeline.arn
}

output "sns_topic_arn" {
  description = "SNS pipeline-alerts topic ARN"
  value       = aws_sns_topic.pipeline_alerts.arn
}

output "archive_lambda_name" {
  description = "Lambda archive-files function name"
  value       = aws_lambda_function.archive_files.function_name
}
