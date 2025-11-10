output "s3_bucket" {
    description = "ARN of the backup uploads bucket"
    value = module.s3-bucket-backup-uploads.bucket.arn
}