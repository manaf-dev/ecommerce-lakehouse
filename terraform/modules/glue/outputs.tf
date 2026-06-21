output "ingest_job_name" {
  description = "Glue ingest-delta job name"
  value       = aws_glue_job.ingest_delta.name
}

output "ingest_job_arn" {
  description = "Glue ingest-delta job ARN"
  value       = aws_glue_job.ingest_delta.arn
}

output "catalog_db_name" {
  description = "Glue catalog database name"
  value       = aws_glue_catalog_database.lakehouse_dwh.name
}
