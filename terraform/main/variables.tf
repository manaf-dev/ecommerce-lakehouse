variable "project" {
  description = "Project name prefix used for all AWS resource names"
  type        = string
}

variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-central-1"
}

variable "bucket" {
  description = "S3 bucket name for the lakehouse (must be globally unique)"
  type        = string
}

variable "alert_email" {
  description = "Email address for SNS pipeline failure alerts"
  type        = string
}

variable "catalog_db_name" {
  description = "Glue Data Catalog database name for Delta tables"
  type        = string
  default     = "lakehouse_dwh"
}
