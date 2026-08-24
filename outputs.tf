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

output "migration_replication_manifest_bucket_arn" {
  description = "ARN of the manifest bucket used by S3 Batch Replication"
  value       = try(aws_s3_bucket.batch_manifest[0].arn, null)
}

output "migration_replication_trigger_lambda_arn" {
  description = "ARN of the Lambda that creates S3 Batch Replication jobs"
  value       = try(module.migration_replication_trigger[0].lambda_function_arn, null)
}
