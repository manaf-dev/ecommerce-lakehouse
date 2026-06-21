variable "bucket" {
  description = "S3 bucket name"
  type        = string
}

variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "catalog_db_name" {
  description = "Glue Data Catalog database name"
  type        = string
}

variable "workgroup_name" {
  description = "Athena workgroup name"
  type        = string
}

variable "glue_ingest_job_arn" {
  description = "ARN of the Glue ingest-delta job"
  type        = string
}

variable "alert_email" {
  description = "Email address for SNS pipeline failure alerts"
  type        = string
}
