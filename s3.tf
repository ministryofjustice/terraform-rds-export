# Backup .bak uploads bucket with sensible defaults
#trivy:ignore:AVD-AWS-0089 Bucket logging not required.
module "s3-bucket-backup-uploads" {
  source = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=9facf9fc8f8b8e3f93ffbda822028534b9a75399" #v9.0.0

  bucket_prefix      = "${var.name}-backup-uploads-${var.environment}-"
  versioning_enabled = true

  ownership_controls = "BucketOwnerEnforced"

  replication_enabled = false
  providers = {
    aws.bucket-replication = aws
  }

  sse_algorithm = "AES256"

  lifecycle_rule = var.lifecycle_rule_backup_uploads
  tags           = var.tags
}


# Creating folder in backup uploads bucket
resource "aws_s3_object" "backup_uploads_folder" {
  bucket = module.s3-bucket-backup-uploads.bucket.id
  key    = "${var.name}-${var.environment}/"
}

# Parquet exports S3 bucket with sensible defaults
#trivy:ignore:AVD-AWS-0089 Bucket logging not required.
module "s3-bucket-parquet-exports" {
  source = "github.com/ministryofjustice/modernisation-platform-terraform-s3-bucket?ref=9facf9fc8f8b8e3f93ffbda822028534b9a75399" #v9.0.0

  bucket_prefix      = "${var.name}-parquet-exports-${var.environment}-"
  versioning_enabled = true

  ownership_controls = "BucketOwnerEnforced"

  replication_enabled = false
  providers = {
    aws.bucket-replication = aws
  }

  sse_algorithm = "AES256"

  lifecycle_rule = var.lifecycle_rule_parquet_exports

  tags = var.tags
}

# Permission to invoke lambda function in bucket
resource "aws_lambda_permission" "allow_bucket" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = module.upload_checker.lambda_function_arn
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3-bucket-backup-uploads.bucket.arn
}

# Bucket Notification to trigger Lambda function
resource "aws_s3_bucket_notification" "backup_uploads" {
  bucket = module.s3-bucket-backup-uploads.bucket.id

  lambda_function {
    lambda_function_arn = module.upload_checker.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}
