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

output "glue_archive_job_name" {
  description = "Glue archive-files job name"
  value       = module.glue.archive_job_name
}

output "crawler_name" {
  description = "Glue crawler name"
  value       = module.glue.crawler_name
}

output "athena_workgroup" {
  description = "Athena workgroup name"
  value       = module.athena.workgroup_name
}
