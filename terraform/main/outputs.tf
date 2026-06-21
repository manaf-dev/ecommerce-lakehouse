output "bucket_name" {
  description = "S3 lakehouse bucket name"
  value       = module.s3.bucket_id
}

output "state_machine_arn" {
  description = "Step Functions pipeline state machine ARN"
  value       = module.step_functions.state_machine_arn
}

output "glue_ingest_job_name" {
  description = "Glue ingest-delta job name"
  value       = module.glue.ingest_job_name
}

output "archive_lambda_name" {
  description = "Lambda archive-files function name"
  value       = module.step_functions.archive_lambda_name
}

output "athena_workgroup" {
  description = "Athena workgroup name"
  value       = module.athena.workgroup_name
}

output "catalog_db_name" {
  description = "Glue Data Catalog database name"
  value       = module.glue.catalog_db_name
}

output "grafana_reader_user_name" {
  description = "IAM user name for Grafana Cloud read-only Athena access"
  value       = module.iam.grafana_reader_user_name
}
