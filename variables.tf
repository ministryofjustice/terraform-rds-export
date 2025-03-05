variable "name" {
  description = "The name of the database"
  type        = string
}
#variable "database_instance_identifier" {
#  description = "The name of the RDS database instance"
#  type        = string
#}

#variable "cron_expression" {
#  description = "Cron expression for scheduling the export task"
#  type        = string
#}

#variable "output_s3_bucket" {
#  description = "The name of the S3 bucket to export the snapshot to"
#  type        = string
#}

variable "vpc_id" {
  description = "The ID of the VPC"
  type        = string
}

variable "database_subnet_ids" {
  description = "The IDs of the subnets in the VPC where the database will be deployed"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "The ARN of the KMS key to use for encrypting the exported snapshot"
  type        = string
}

variable "tags" {
  type        = map(string)
  description = "Common tags to be used by all resources"
}
