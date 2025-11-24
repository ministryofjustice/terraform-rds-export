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

output "database_export_scanner_role_arn" {
  description = "ARN of the IAM role for the database export scanner. This role is used to create glue tables"
  value       = module.database_export_scanner.lambda_role_arn
}

output "database_export_processor_role_arn" {
  description = "ARN of the IAM role for the database export processor. This role is used to export data to S3"
  value       = module.database_export_processor.lambda_role_arn
}
