# Security group for RDS instance
resource "aws_security_group" "database" {
  name        = "${var.name}-database"
  description = "Allow inbound traffic to database"
  vpc_id      = data.aws_vpc.vpc.id

  ingress {
    from_port   = 1433
    to_port     = 1433
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.vpc.cidr_block]
  }
}

# Subnet group for database
resource "aws_db_subnet_group" "database" {
  name       = "${var.name}-database-backup-export"
  subnet_ids = var.database_subnet_ids
}

# Create parameter group for database
resource "aws_db_parameter_group" "database" {
  name        = "${var.name}-backup-export"
  family      = "sqlserver-se-15.0"
  description = "Parameter group for SQL Server Standard Edition"
}

# Create option group for database
resource "aws_db_option_group" "database" {
  name                     = "${var.name}-backup-export"
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

# Deploy RDS instance for MS SQL Server
resource "aws_db_instance" "database" {
  allocated_storage           = 100
  storage_type                = "gp2"
  engine                      = "sqlserver-se"
  engine_version              = "15.00.4420.2.v1"
  license_model               = "license-included"
  instance_class              = "db.m5.2xlarge"
  identifier                  = "${var.name}-sql-server-backup-export"
  username                    = "admin"
  manage_master_user_password = true
  parameter_group_name        = aws_db_parameter_group.database.name
  option_group_name           = aws_db_option_group.database.name
  skip_final_snapshot         = true
  vpc_security_group_ids      = [aws_security_group.database.id]
  db_subnet_group_name        = aws_db_subnet_group.database.name
}
