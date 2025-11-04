# Dynamically fetch valid engine versions for this region
data "aws_rds_engine_version" "selected" {
  engine = var.engine
}

locals {
  engine_version_valid = contains(
    [for v in data.aws_rds_engine_version.selected.valid_versions : v.version],
    var.engine_version
  )
}

# Validate the input
check "engine_version_valid" {
  assert {
    condition     = local.engine_version_valid
    error_message = "Invalid engine_version '${var.engine_version}'. Must be one of the valid RDS versions for ${var.engine}."
  }
}

# Security group for RDS instance
resource "aws_security_group" "database" {
  name        = "${var.name}-${var.environment}-database"
  description = "Allow inbound traffic to database"
  vpc_id      = data.aws_vpc.vpc.id

  ingress {
    description = "Allow inbound traffic from VPC CIDR block"
    from_port   = 1433
    to_port     = 1433
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.vpc.cidr_block]
  }
}

# Subnet group for database
resource "aws_db_subnet_group" "database" {
  name       = "${var.name}-${var.environment}-database-backup-export"
  subnet_ids = var.database_subnet_ids
}

# Create parameter group for database
resource "aws_db_parameter_group" "database" {
  name        = "${var.name}-${var.environment}-backup-export"
  family      = "sqlserver-se-15.0"
  description = "Parameter group for SQL Server Standard Edition"
}

# Create option group for database
resource "aws_db_option_group" "database" {
  name                     = "${var.name}-${var.environment}-backup-export"
  engine_name              = "sqlserver-se"
  major_engine_version     = "15.00"
  option_group_description = "Used by the database for loading backups and exporting to S3"

  option {
    option_name = "SQLSERVER_BACKUP_RESTORE"

    option_settings {
      name  = "IAM_ROLE_ARN"
      value = aws_iam_role.database_restore.arn
    }
  }
}
