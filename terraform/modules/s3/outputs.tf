output "bucket_id" {
  description = "S3 bucket name (ID)"
  value       = aws_s3_bucket.lakehouse.id
}

output "bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.lakehouse.arn
}
