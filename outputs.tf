output "backup_uploads_s3_bucket_arn" {
    description = "ARN of the backup uploads bucket"
    value = module.s3-bucket-backup-uploads.bucket.arn
}