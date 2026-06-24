variable "bucket" {
  description = "S3 bucket name"
  type        = string
}

variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "glue_role_arn" {
  description = "ARN of the Glue execution IAM role"
  type        = string
}

variable "catalog_db_name" {
  description = "Glue Data Catalog database name"
  type        = string
  default     = "lakehouse_dwh"
}

variable "workgroup_name" {
  description = "Athena workgroup name for DDL queries during catalog registration"
  type        = string
}
