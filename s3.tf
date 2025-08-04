# Create S3 Bucket for SQL Server backup files to be uploaded to
module "s3_bucket_backup_uploads" {
  source = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=v7.0.0"

  bucket_name        = "${var.name}-backup-uploads-"
  versioning_enabled = false
  sse_algorithm      = "AES256"

  # Refer to the below section "Replication" before enabling replication
  replication_enabled = false
  # Below variable and providers configuration is only relevant if 'replication_enabled' is set to true
  # replication_region                       = "eu-west-2"
  # providers = {
  #   # Here we use the default provider Region for replication. Destination buckets can be within the same Region as the
  #   # source bucket. On the other hand, if you need to enable cross-region replication, please contact the Modernisation
  #   # Platform team to add a new provider for the additional Region.
  #   # Leave this provider block in even if you are not using replication
  #   aws.bucket-replication = aws
  # }

  lifecycle_rule = [
    {
      id      = "main"
      enabled = "Enabled"
      prefix  = ""

      tags = {
        rule      = "log"
        autoclean = "true"
      }

      transition = [
        {
          days          = 90
          storage_class = "STANDARD_IA"
          }, {
          days          = 365
          storage_class = "GLACIER"
        }
      ]

      expiration = {
        days = 730
      }

      noncurrent_version_transition = [
        {
          days          = 90
          storage_class = "STANDARD_IA"
          }, {
          days          = 365
          storage_class = "GLACIER"
        }
      ]

      noncurrent_version_expiration = {
        days = 730
      }
    }
  ]

  tags = var.tags
}

# Creating folder to drop .bak files in
resource "aws_s3_object" "backup_uploads_folder" {
  bucket = module.s3_bucket_backup_uploads.bucket.id
  key    = "${var.name}/"
}

# Create bucket to store exported parquet files
module "s3_bucket_parquet_exports" {
  source = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=v7.0.0"

  bucket_name        = "${var.name}-parquet-exports-"
  versioning_enabled = false
  sse_algorithm      = "AES256"

  # Refer to the below section "Replication" before enabling replication
  replication_enabled = false
  # Below variable and providers configuration is only relevant if 'replication_enabled' is set to true
  # replication_region                       = "eu-west-2"
  # providers = {
  #   # Here we use the default provider Region for replication. Destination buckets can be within the same Region as the
  #   # source bucket. On the other hand, if you need to enable cross-region replication, please contact the Modernisation
  #   # Platform team to add a new provider for the additional Region.
  #   # Leave this provider block in even if you are not using replication
  #   aws.bucket-replication = aws
  # }

  lifecycle_rule = [
    {
      id      = "main"
      enabled = "Enabled"
      prefix  = ""

      tags = {
        rule      = "log"
        autoclean = "true"
      }

      transition = [
        {
          days          = 90
          storage_class = "STANDARD_IA"
          }, {
          days          = 365
          storage_class = "GLACIER"
        }
      ]

      expiration = {
        days = 730
      }

      noncurrent_version_transition = [
        {
          days          = 90
          storage_class = "STANDARD_IA"
          }, {
          days          = 365
          storage_class = "GLACIER"
        }
      ]

      noncurrent_version_expiration = {
        days = 730
      }
    }
  ]

  tags = var.tags
}

# Lambda function to check if all files have been uploaded to the S3 bucket
resource "aws_lambda_permission" "allow_bucket" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = module.upload_checker.lambda_function_arn
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3_bucket_backup_uploads.bucket.arn
}

# Bucket Notification to trigger Lambda function
resource "aws_s3_bucket_notification" "backup_uploads" {
  bucket = module.s3_bucket_backup_uploads.bucket.id

  lambda_function {
    lambda_function_arn = module.upload_checker.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}
