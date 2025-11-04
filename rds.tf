data "aws_rds_engine_version" "selected" {
  engine         = var.engine
  engine_version = var.engine_version
}

# Fail early if the engine version is invalid
resource "null_resource" "validate_engine_version" {
  count = try(data.aws_rds_engine_version.selected.engine_version, null) != null ? 0 : 1

  provisioner "local-exec" {
    command = "echo 'Invalid engine_version ${var.engine_version} for engine ${var.engine}' && exit 1"
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
  engine_name              = var.engine
  major_engine_version     = substr(var.engine_version, 0, 5)
  option_group_description = "Used by the database for loading backups and exporting to S3"

  option {
    option_name = "SQLSERVER_BACKUP_RESTORE"

    option_settings {
      name  = "IAM_ROLE_ARN"
      value = aws_iam_role.database_restore.arn
    }
  }
}
