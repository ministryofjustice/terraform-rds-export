# Data block for VPC with ID
data "aws_vpc" "vpc" {
  id = var.vpc_id
}

# Data block for current AWS account ID
data "aws_caller_identity" "current" {}

# Data block for AWS region
data "aws_region" "current" {}
