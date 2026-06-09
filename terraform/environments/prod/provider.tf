terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  # S3 backend — bucket and region are supplied at init time via -backend-config flags.
  # CD workflow passes these from GitHub variables (TF_STATE_BUCKET, AWS_REGION).
  # First-time local setup:
  #   terraform -chdir=terraform/environments/prod init \
  #     -backend-config="bucket=<project>-tfstate" \
  #     -backend-config="region=eu-central-1"
  backend "s3" {
    key     = "ecommerce-lakehouse/prod/terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.region
}
