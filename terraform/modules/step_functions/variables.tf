variable "bucket" {
  description = "S3 bucket name"
  type        = string
}

variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "sfn_role_arn" {
  description = "ARN of the Step Functions execution IAM role"
  type        = string
}

variable "eventbridge_role_arn" {
  description = "ARN of the EventBridge execution IAM role"
  type        = string
}

variable "workgroup_name" {
  description = "Athena workgroup name"
  type        = string
}

variable "alert_email" {
  description = "Email address for SNS pipeline failure alerts"
  type        = string
}
