output "ingest_job_name" {
  description = "Glue ingest-delta job name"
  value       = aws_glue_job.ingest_delta.name
}

output "ingest_job_arn" {
  description = "Glue ingest-delta job ARN"
  value       = aws_glue_job.ingest_delta.arn
}

output "archive_job_name" {
  description = "Glue archive-files job name"
  value       = aws_glue_job.archive_files.name
}

output "archive_job_arn" {
  description = "Glue archive-files job ARN"
  value       = aws_glue_job.archive_files.arn
}

output "crawler_name" {
  description = "Glue crawler name"
  value       = aws_glue_crawler.lakehouse.name
}

output "catalog_db_name" {
  description = "Glue catalog database name"
  value       = aws_glue_catalog_database.lakehouse_dwh.name
}
