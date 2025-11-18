# Data block for VPC with ID
data "aws_vpc" "vpc" {
  id = var.vpc_id
}

# Data block for current AWS account ID
data "aws_caller_identity" "current" {}

# Data block for AWS region
data "aws_region" "current" {}

# Data block for master user password secret for RDS database
data "aws_secretsmanager_secret_version" "master_user_secret" {
  secret_id = var.master_user_secret_id
}
