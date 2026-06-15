data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ─── ARNs computed from naming convention ──────────────────────────────────────
# Constructing ARNs locally avoids circular module dependencies:
# iam ← (no module deps)  glue ← iam  step_functions ← iam
locals {
  account_id                = data.aws_caller_identity.current.account_id
  region                    = data.aws_region.current.region
  glue_ingest_job_arn       = "arn:aws:glue:${local.region}:${local.account_id}:job/${var.project}-ingest-delta"
  glue_archive_job_arn      = "arn:aws:glue:${local.region}:${local.account_id}:job/${var.project}-archive-files"
  glue_fix_catalog_job_arn  = "arn:aws:glue:${local.region}:${local.account_id}:job/${var.project}-fix-catalog-timestamps"
  crawler_arn               = "arn:aws:glue:${local.region}:${local.account_id}:crawler/${var.project}-crawler"
  athena_workgroup_arn      = "arn:aws:athena:${local.region}:${local.account_id}:workgroup/${var.project}-workgroup"
  sns_topic_arn             = "arn:aws:sns:${local.region}:${local.account_id}:${var.project}-pipeline-alerts"
  state_machine_arn         = "arn:aws:states:${local.region}:${local.account_id}:stateMachine:${var.project}-pipeline"
}

# ─── S3 ────────────────────────────────────────────────────────────────────────
module "s3" {
  source  = "../../modules/s3"
  bucket  = var.bucket
  project = var.project
}

# ─── IAM ───────────────────────────────────────────────────────────────────────
module "iam" {
  source                   = "../../modules/iam"
  bucket                   = var.bucket
  project                  = var.project
  glue_ingest_job_arn      = local.glue_ingest_job_arn
  glue_archive_job_arn     = local.glue_archive_job_arn
  glue_fix_catalog_job_arn = local.glue_fix_catalog_job_arn
  crawler_arn              = local.crawler_arn
  athena_workgroup_arn     = local.athena_workgroup_arn
  sns_topic_arn            = local.sns_topic_arn
  state_machine_arn        = local.state_machine_arn
}

# ─── Glue ──────────────────────────────────────────────────────────────────────
module "glue" {
  source          = "../../modules/glue"
  bucket          = var.bucket
  project         = var.project
  glue_role_arn   = module.iam.glue_role_arn
  catalog_db_name = "lakehouse_dwh"

  depends_on = [module.s3]
}

# ─── Athena ────────────────────────────────────────────────────────────────────
module "athena" {
  source  = "../../modules/athena"
  bucket  = var.bucket
  project = var.project

  depends_on = [module.s3]
}

# ─── Step Functions ────────────────────────────────────────────────────────────
module "step_functions" {
  source               = "../../modules/step_functions"
  bucket               = var.bucket
  project              = var.project
  sfn_role_arn         = module.iam.sfn_role_arn
  eventbridge_role_arn = module.iam.eventbridge_role_arn
  workgroup_name       = module.athena.workgroup_name
  alert_email          = var.alert_email
}
