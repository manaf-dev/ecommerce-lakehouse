terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    key     = "terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

module "s3" {
  source  = "../modules/s3"
  bucket  = var.bucket
  project = var.project
}

module "iam" {
  source         = "../modules/iam"
  bucket         = var.bucket
  project        = var.project
  catalog_db     = var.catalog_db_name
  scripts_prefix = "scripts/"
}

module "glue" {
  source          = "../modules/glue"
  bucket          = var.bucket
  project         = var.project
  glue_role_arn   = module.iam.glue_role_arn
  catalog_db_name = var.catalog_db_name

  depends_on = [module.s3, module.iam]
}

module "athena" {
  source  = "../modules/athena"
  bucket  = var.bucket
  project = var.project

  depends_on = [module.s3]
}

module "step_functions" {
  source              = "../modules/step_functions"
  bucket              = var.bucket
  project             = var.project
  catalog_db_name     = var.catalog_db_name
  workgroup_name      = module.athena.workgroup_name
  glue_ingest_job_arn = module.glue.ingest_job_arn
  alert_email         = var.alert_email

  depends_on = [module.glue, module.athena, module.s3]
}
