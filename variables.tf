variable "name" {
  description = "The name of the project. Combined with the environment (<name>-<environment>) to create the RDS DB instance identifier."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.name))
    error_message = "Name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "db_name" {
  description = "The name of the database. Used for Glue, Athena, and restore process in RDS. Only lowercase letters, numbers, and the underscore character."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.db_name))
    error_message = "Database name must contain only lowercase letters, numbers, and underscores."
  }
}

variable "database_refresh_mode" {
  description = "Specifies the type of database refresh: 'full' for complete refresh or 'incremental' for partial updates."
  type        = string
  validation {
    condition     = contains(["full", "incremental"], lower(var.database_refresh_mode))
    error_message = "Database refresh mode must be either 'full' or 'incremental'."
  }
}

variable "vpc_id" {
  description = "The ID of the VPC."
  type        = string
  validation {
    condition     = can(regex("^vpc-", var.vpc_id))
    error_message = "VPC ID must be a valid AWS VPC identifier."
  }
}

variable "database_subnet_ids" {
  description = "The IDs of the subnets in the VPC where the database will be deployed."
  type        = list(string)
  validation {
    condition = alltrue([
      for subnet_id in var.database_subnet_ids : can(regex("^subnet-", subnet_id))
    ])
    error_message = "All subnet IDs must be valid AWS subnet identifiers."
  }
}

variable "kms_key_arn" {
  description = "The ARN of the KMS key to use for secrets and exported snapshots."
  type        = string
  validation {
    condition     = can(regex("^arn:aws:kms:", var.kms_key_arn))
    error_message = "KMS key ARN must be a valid AWS KMS key ARN."
  }
}

variable "master_user_secret_id" {
  description = "The ARN of the secret containing the master user password to use for the RDS DB database."
  type        = string
  validation {
    condition     = can(regex("^arn:aws:secretsmanager:", var.master_user_secret_id))
    error_message = "Master user secret ID must be a valid AWS Secrets Manager ARN."
  }
}

variable "tags" {
  type        = map(string)
  description = "Common tags to be used by all resources."
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g., dev, test, staging, prod). Used for resource naming, tagging, and conditional settings."
}

variable "output_parquet_file_size" {
  type        = number
  description = "Approximate target size (in MiB) for each Parquet file produced by the database-export lambda."
  default     = 10
  validation {
    condition     = var.output_parquet_file_size > 0 && var.output_parquet_file_size <= 500
    error_message = "Output parquet file size must be between 1 and 500 MiB."
  }
}

variable "max_concurrency" {
  type        = number
  description = "Maximum number of database_export lambda functions to run in parallel."
  default     = 5
  validation {
    condition     = var.max_concurrency > 0 && var.max_concurrency <= 20
    error_message = "Max concurrency must be between 1 and 20."
  }
}

variable "engine_version" {
  description = "The SQL Server engine version for the RDS instance."
  type        = string
  default     = "15.00.4420.2.v1"
  validation {
    condition     = can(regex("^\\d+\\.\\d+\\..+$", var.engine_version))
    error_message = "Engine version must match SQL Server version format (e.g., 15.00.4420.2.v1)."
  }
}

variable "get_views" {
  description = "Whether to extract views from the database backup."
  type        = bool
  default     = false
}

variable "lifecycle_rule_parquet_exports" {
  description = "List of maps containing configuration of object lifecycle management for the parquet_exports S3 buckets."
  type        = any
  default = [{
    id      = "main"
    enabled = "Enabled"
    prefix  = ""
    tags = {
      rule      = "log"
      autoclean = "true"
    }
    transition = [
      {
        days          = 90
        storage_class = "STANDARD_IA"
        }, {
        days          = 365
        storage_class = "GLACIER"
      }
    ]
    expiration = {
      days = 730
    }
    noncurrent_version_transition = [
      {
        days          = 90
        storage_class = "STANDARD_IA"
        }, {
        days          = 365
        storage_class = "GLACIER"
      }
    ]
    noncurrent_version_expiration = {
      days = 730
    }
  }]
}

variable "lifecycle_rule_backup_uploads" {
  description = "List of maps containing configuration of object lifecycle management for the backup_uploads S3 bucket."
  type        = any
  default = [{
    id      = "main"
    enabled = "Enabled"
    prefix  = ""
    tags = {
      rule      = "log"
      autoclean = "true"
    }
    transition = [
      {
        days          = 90
        storage_class = "STANDARD_IA"
        }, {
        days          = 365
        storage_class = "GLACIER"
      }
    ]
    expiration = {
      days = 730
    }
    noncurrent_version_transition = [
      {
        days          = 90
        storage_class = "STANDARD_IA"
        }, {
        days          = 365
        storage_class = "GLACIER"
      }
    ]
    noncurrent_version_expiration = {
      days = 730
    }
  }]
}
