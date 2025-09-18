# Create S3 Bucket for SQL Server backup files to be uploaded to
# TO DO: Add lifecycle configuration 
#trivy:ignore:AVD-AWS-0089 # Bucket logging not required
#trivy:ignore:AVD-AWS-0090 # Bucket versioning not required - TODO: May add later

module "backup_uploads" {
  source             = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=v9.0.0"
  providers = {
    aws.bucket-replication = aws.bucket-replication
  }
  bucket_policy = [
    jsonencode({
      Version   = "2012-10-17",
      Statement = [
        {
          Sid       = "AccountBucketLevel",
          Effect    = "Allow",
          Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" },
          Action    = [
            "s3:ListBucket",
            "s3:ListBucketMultipartUploads"
          ],
          Resource  = ["arn:aws:s3:::${local.backup_uploads_prefix}*"]
        },
        {
          Sid       = "AccountObjectLevel",
          Effect    = "Allow",
          Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" },
          Action    = [
            "s3:PutObject",
            "s3:AbortMultipartUpload",
            "s3:PutObjectTagging"
          ],
          Resource  = ["arn:aws:s3:::${local.backup_uploads_prefix}*/*"]
        }
      ]
    })
  ]
  bucket_prefix      = "${var.name}-backup-uploads-${var.environment}-"
  custom_kms_key     = var.kms_key_arn
  versioning_enabled = true
  sse_algorithm = "AES256"
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

# Creating folder to drop .bak files in
resource "aws_s3_object" "backup_uploads_folder" {
  bucket = module.backup_uploads.bucket.id
  key    = "${var.name}/"
}

# Create bucket to store exported parquet files
#trivy:ignore:AVD-AWS-0089 # Bucket logging not required
#trivy:ignore:AVD-AWS-0090 # Bucket versioning not required

module "parquet_exports" {
  source             = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=v9.0.0"
  providers = {
    aws.bucket-replication = aws.bucket-replication
  }
  bucket_prefix      = "${var.name}-parquet-exports-${var.environment}-"
  custom_kms_key     = var.kms_key_arn
  versioning_enabled = true
  sse_algorithm = "AES256"
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
