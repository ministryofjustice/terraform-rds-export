output "backup_uploads_s3_bucket_arn" {
  description = "ARN of the backup uploads bucket"
  value       = module.s3-bucket-backup-uploads.bucket.arn
}

output "backup_uploads_s3_bucket_id" {
  description = "Name of the backup uploads bucket"
  value       = module.s3-bucket-backup-uploads.bucket.id
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic to subscribe to"
  value       = aws_sns_topic.sfn_events.arn
}
