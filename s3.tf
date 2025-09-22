# Create S3 Bucket for SQL Server backup files to be uploaded to
# TO DO: Add lifecycle configuration 
#trivy:ignore:AVD-AWS-0089 # Bucket logging not required
#trivy:ignore:AVD-AWS-0090 # Bucket versioning not required - TODO: May add later
locals {
  backup_uploads_prefix = "${var.name}-backup-uploads-${var.environment}-"
}

module "backup_uploads" {
  source    = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=v9.0.0"
  providers = { aws.bucket-replication = aws.bucket-replication }

  bucket_prefix       = local.backup_uploads_prefix
  custom_kms_key      = var.kms_key_arn
  sse_algorithm       = "aws:kms"
  versioning_enabled  = true
  ownership_controls  = "BucketOwnerEnforced"
  replication_enabled = false

  # S3 actions only
  bucket_policy_v2 = [
    # Bucket-level perms
    {
      effect     = "Allow"
      actions    = ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"]
      principals = { type = "AWS", identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"] }
    },
    # Object-level perms
    {
      effect     = "Allow"
      actions    = ["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts", "s3:PutObjectTagging"]
      principals = { type = "AWS", identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"] }
    }
  ]

  lifecycle_rule = [
    {
      id      = "main"
      enabled = "Enabled"
      filter  = { prefix = "" }

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

      noncurrent_version_expiration = { days = 730 }
    }
  ]

  tags = var.tags
}

# Creating folder to drop .bak files in
resource "aws_s3_object" "backup_uploads_folder" {
  bucket = module.backup_uploads.bucket.id
  key    = "${var.name}/"
  content = ""
}

# Create bucket to store exported parquet files
#trivy:ignore:AVD-AWS-0089 # Bucket logging not required
#trivy:ignore:AVD-AWS-0090 # Bucket versioning not required

module "parquet_exports" {
  source = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=v9.0.0"
  providers = {
    aws.bucket-replication = aws.bucket-replication
  }
  bucket_prefix      = "${var.name}-parquet-exports-${var.environment}-"
  custom_kms_key     = var.kms_key_arn
  sse_algorithm       = "aws:kms"
  versioning_enabled = true
  # to disable ACLs in preference of BucketOwnership controls as per https://aws.amazon.com/blogs/aws/heads-up-amazon-s3-security-changes-are-coming-in-april-of-2023/ set:
  ownership_controls = "BucketOwnerEnforced"

  # Refer to the below section "Replication" before enabling replication
  replication_enabled = false

  lifecycle_rule = [
    {
      id      = "main"
      enabled = "Enabled"
      filter  = { prefix = "" }

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

      noncurrent_version_expiration = { days = 730 }
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
  source_arn    = module.backup_uploads.bucket.arn
}

# Bucket Notification to trigger Lambda function
resource "aws_s3_bucket_notification" "backup_uploads" {
  bucket = module.backup_uploads.bucket.id

  lambda_function {
    lambda_function_arn = module.upload_checker.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}
