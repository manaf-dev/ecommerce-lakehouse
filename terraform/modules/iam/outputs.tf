output "glue_role_arn" {
  description = "Glue execution role ARN"
  value       = aws_iam_role.glue.arn
}
