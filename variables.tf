variable "name" {
  description = "The name of the database in RDS"
  type        = string
}

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

variable "master_user_secret_id" {
  description = "The ARN of the secret containing the master user password for the RDS database"
}

variable "tags" {
  type        = map(string)
  description = "Common tags to be used by all resources"
}
