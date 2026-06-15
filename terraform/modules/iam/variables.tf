variable "bucket" {
  description = "S3 bucket name"
  type        = string
}

variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "glue_ingest_job_arn" {
  description = "ARN of the Glue ingest-delta job"
  type        = string
}

variable "glue_archive_job_arn" {
  description = "ARN of the Glue archive-files job"
  type        = string
}

variable "glue_fix_catalog_job_arn" {
  description = "ARN of the Glue fix-catalog-timestamps job"
  type        = string
}

variable "crawler_arn" {
  description = "ARN of the Glue crawler"
  type        = string
}

variable "athena_workgroup_arn" {
  description = "ARN of the Athena workgroup"
  type        = string
}

variable "sns_topic_arn" {
  description = "ARN of the SNS pipeline-alerts topic"
  type        = string
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine (for EventBridge role)"
  type        = string
}
