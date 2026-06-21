# ─── Catalog database ──────────────────────────────────────────────────────────
resource "aws_glue_catalog_database" "lakehouse_dwh" {
  name = var.catalog_db_name
}

resource "aws_s3_object" "ingest_delta_script" {
  bucket = var.bucket
  key    = "scripts/ingest_delta.py"
  source = "${path.module}/../../../src/glue_jobs/ingest_delta.py"
  etag   = filemd5("${path.module}/../../../src/glue_jobs/ingest_delta.py")
}

locals {
  delta_spark_conf = join(" ", [
    "--conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension",
    "--conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog",
    "--conf spark.delta.logStore.class=org.apache.spark.sql.delta.storage.S3SingleDriverLogStore",
  ])
}

resource "aws_glue_job" "ingest_delta" {
  name              = "${var.project}-ingest-delta"
  role_arn          = var.glue_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  max_retries       = 0
  timeout           = 2880

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket}/scripts/ingest_delta.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"                 = "delta"
    "--conf"                             = local.delta_spark_conf
    "--extra-py-files"                   = "s3://${var.bucket}/scripts/utils.zip"
    "--additional-python-modules"        = "pandas==2.2.3,openpyxl==3.1.5"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = "/aws-glue/jobs/${var.project}-ingest-delta"
    "--enable-metrics"                   = ""
    "--TempDir"                          = "s3://${var.bucket}/temp/"
    "--catalog_db"                       = var.catalog_db_name
  }

  execution_property {
    max_concurrent_runs = 1
  }
}
