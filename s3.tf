# Create S3 Bucket for SQL Server backup files to be uploaded to
resource "aws_s3_bucket" "backup_uploads" {
  bucket_prefix = "${var.name}-backup-uploads-"
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
resource "aws_s3_bucket" "parquet_exports" {
  bucket_prefix = "${var.name}-parquet-exports-"
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
