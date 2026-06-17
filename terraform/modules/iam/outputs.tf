output "glue_role_arn" {
  description = "Glue execution role ARN"
  value       = aws_iam_role.glue.arn
}

output "sfn_role_arn" {
  description = "Step Functions execution role ARN"
  value       = aws_iam_role.sfn.arn
}

output "eventbridge_role_arn" {
  description = "EventBridge execution role ARN"
  value       = aws_iam_role.eventbridge.arn
}

output "grafana_reader_user_name" {
  description = "IAM user name for Grafana Cloud — run 'aws iam create-access-key --user-name <value>' to generate credentials"
  value       = aws_iam_user.grafana_reader.name
}
