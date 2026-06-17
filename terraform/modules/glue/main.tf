# ─── Catalog database ──────────────────────────────────────────────────────────
resource "aws_glue_catalog_database" "lakehouse_dwh" {
  name = var.catalog_db_name
}

# ─── Glue job scripts (S3 objects) ────────────────────────────────────────────
resource "aws_s3_object" "ingest_delta_script" {
  bucket = var.bucket
  key    = "scripts/ingest_delta.py"
  source = "${path.module}/../../../src/glue_jobs/ingest_delta.py"
  etag   = filemd5("${path.module}/../../../src/glue_jobs/ingest_delta.py")
}

resource "aws_s3_object" "archive_files_script" {
  bucket = var.bucket
  key    = "scripts/archive_files.py"
  source = "${path.module}/../../../src/glue_jobs/archive_files.py"
  etag   = filemd5("${path.module}/../../../src/glue_jobs/archive_files.py")
}

resource "aws_s3_object" "fix_catalog_timestamps_script" {
  bucket = var.bucket
  key    = "scripts/fix_catalog_timestamps.py"
  source = "${path.module}/../../../src/glue_jobs/fix_catalog_timestamps.py"
  etag   = filemd5("${path.module}/../../../src/glue_jobs/fix_catalog_timestamps.py")
}

# ─── Glue job: ingest_delta (PySpark, Glue 5.0) ────────────────────────────────
resource "aws_glue_job" "ingest_delta" {
  name              = "${var.project}-ingest-delta"
  role_arn          = var.glue_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  max_retries       = 0
  timeout           = 2880 # 48 hours max

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket}/scripts/ingest_delta.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"                 = "delta"
    "--conf"                             = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
    "--extra-py-files"                   = "s3://${var.bucket}/scripts/utils.zip"
    "--additional-python-modules"        = "pandas==2.2.3,openpyxl==3.1.5"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = "/aws-glue/jobs/${var.project}-ingest-delta"
    "--enable-metrics"                   = ""
    "--TempDir"                          = "s3://${var.bucket}/temp/"
  }

  execution_property {
    max_concurrent_runs = 6
  }

  depends_on = [aws_s3_object.ingest_delta_script]
}

# ─── Glue job: archive_files (Python Shell, Glue 3.0) ─────────────────────────
resource "aws_glue_job" "archive_files" {
  name         = "${var.project}-archive-files"
  role_arn     = var.glue_role_arn
  glue_version = "3.0"
  max_capacity = 0.0625
  max_retries  = 0
  timeout      = 60

  command {
    name            = "pythonshell"
    script_location = "s3://${var.bucket}/scripts/archive_files.py"
    python_version  = "3.9"
  }

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = "/aws-glue/jobs/${var.project}-archive-files"
  }

  execution_property {
    max_concurrent_runs = 1
  }

  depends_on = [aws_s3_object.archive_files_script, aws_cloudwatch_log_group.archive_files]
}

# ─── Glue job: fix_catalog_timestamps (Python Shell, Glue 3.0) ────────────────
resource "aws_glue_job" "fix_catalog_timestamps" {
  name         = "${var.project}-fix-catalog-timestamps"
  role_arn     = var.glue_role_arn
  glue_version = "3.0"
  max_capacity = 0.0625
  max_retries  = 0
  timeout      = 5

  command {
    name            = "pythonshell"
    script_location = "s3://${var.bucket}/scripts/fix_catalog_timestamps.py"
    python_version  = "3.9"
  }

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = "/aws-glue/jobs/${var.project}-fix-catalog-timestamps"
    "--catalog_db"                       = var.catalog_db_name
    "--tables"                           = "products,orders,order_items"
  }

  execution_property {
    max_concurrent_runs = 1
  }

  depends_on = [aws_s3_object.fix_catalog_timestamps_script, aws_cloudwatch_log_group.fix_catalog_timestamps]
}

# ─── CloudWatch log groups for Glue jobs ─────────────────────────────────────
resource "aws_cloudwatch_log_group" "crawler" {
  name              = "/aws-glue/crawlers"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "ingest_delta" {
  name              = "/aws-glue/jobs/${var.project}-ingest-delta"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "archive_files" {
  name              = "/aws-glue/jobs/${var.project}-archive-files"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "fix_catalog_timestamps" {
  name              = "/aws-glue/jobs/${var.project}-fix-catalog-timestamps"
  retention_in_days = 30
}

# ─── Glue crawler ──────────────────────────────────────────────────────────────
resource "aws_glue_crawler" "lakehouse" {
  depends_on = [aws_cloudwatch_log_group.crawler]
  name          = "${var.project}-crawler"
  role          = var.glue_role_arn
  database_name = aws_glue_catalog_database.lakehouse_dwh.name

  delta_target {
    delta_tables = [
      "s3://${var.bucket}/lakehouse-dwh/products/",
      "s3://${var.bucket}/lakehouse-dwh/orders/",
      "s3://${var.bucket}/lakehouse-dwh/order_items/",
    ]
    write_manifest             = false
    create_native_delta_table  = true
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }
}
