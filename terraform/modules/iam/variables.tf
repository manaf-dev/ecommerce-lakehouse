variable "bucket" {
  description = "S3 bucket name"
  type        = string
}

variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "catalog_db" {
  description = "Glue Data Catalog database name"
  type        = string
}

variable "scripts_prefix" {
  description = "S3 prefix for Glue job scripts"
  type        = string
  default     = "scripts/"
}
