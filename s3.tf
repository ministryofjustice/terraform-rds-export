# Create S3 Bucket for SQL Server backup files to be uploaded to
#trivy:ignore:AVD-AWS-0089 # Bucket logging not required
#trivy:ignore:AVD-AWS-0090 # Bucket versioning not required - TODO: May add later
#trivy:ignore:AVD-AWS-0132 # Bucket encrypted with AES-256
resource "aws_s3_bucket" "backup_uploads" {
  bucket_prefix = "${var.name}-backup-uploads-"

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}

# Block Public Access
resource "aws_s3_bucket_public_access_block" "backup_uploads" {
  bucket                  = aws_s3_bucket.backup_uploads.bucket
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Create bucket to store exported parquet files
#trivy:ignore:AVD-AWS-0089 # Bucket logging not required
#trivy:ignore:AVD-AWS-0090 # Bucket versioning not required
#trivy:ignore:AVD-AWS-0132 # Bucket encrypted with AES-256
resource "aws_s3_bucket" "parquet_exports" {
  bucket_prefix = "${var.name}-parquet-exports-"

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}

# Block Public Access
resource "aws_s3_bucket_public_access_block" "parquet_exports" {
  bucket                  = aws_s3_bucket.parquet_exports.bucket
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


# Lambda function to check if all files have been uploaded to the S3 bucket
resource "aws_lambda_permission" "allow_bucket" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = module.upload_checker.lambda_function_arn
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.backup_uploads.arn
}

# Bucket Notification to trigger Lambda function
resource "aws_s3_bucket_notification" "backup_uploads" {
  bucket = aws_s3_bucket.backup_uploads.bucket

  lambda_function {
    lambda_function_arn = module.upload_checker.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}
