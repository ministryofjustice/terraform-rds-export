variable "name" {
  description = "The name of the project"
  type        = string
}

variable "db_name" {
  description = "The name of the database. Used for Glue, Athena, and restore process in RDS. Only lowercase letters, numbers, and the underscore character"
  type        = string
}

variable "database_refresh_mode" {
  description = "Specifies the type of database refresh: 'full' for complete refresh or 'incremental' for partial updates."
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
  description = "The ARN of the KMS key to use for secretes and exported snapshot"
  type        = string
}

variable "master_user_secret_id" {
  description = "The ARN of the secret containing the master user password to use for the RDS DB database"
}

variable "tags" {
  type        = map(string)
  description = "Common tags to be used by all resources"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g., dev, test, staging, prod). Used for resource naming, tagging, and conditional settings."
}

variable "output_parquet_file_size" {
  type        = number
  description = "Approximate target size (in MiB) for each Parquet file produced by the database-export lambda"
  default     = 10
}

variable "max_concurrency" {
  type        = number
  description = "Maximum number of database-export lambda run in parallel."
  default     = 5
}
