locals {
  tags = {
    business_unit          = "HMPPS"
    application            = "rds-s3-export-test"
    is_production          = "false"
    team_name              = "DMET"
    namespace              = "test"
    environment_name       = "local"
    infrastructure_support = "HMPPS DMET Team"
  }
}

data "aws_caller_identity" "current" {}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.17.0"

  name = "rds-s3-export-test"
  cidr = "10.0.0.0/16"

  azs             = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true

  tags = local.tags
}

#resource "aws_db_subnet_group" "test" {
#  name       = "rds-s3-export-test"
#  subnet_ids = module.vpc.private_subnets
#
#  tags = local.tags
#}

# Moto does not support rds subnet groups
# Cannot use cloud platform rds module due to this
#resource "aws_db_instance" "test_db" {
#  identifier           = "rds-s3-export-test"
#  db_subnet_group_name = aws_db_subnet_group.test.name
#  engine               = "postgres"
#  engine_version       = "16.3"
#  instance_class       = "db.t3.micro"
#  username             = "postgres"
#  password             = "password"
#  allocated_storage    = 20
#  skip_final_snapshot  = true
#}

#module "calculate_release_dates_api_rds" {
#  source                 = "github.com/ministryofjustice/cloud-platform-terraform-rds-instance?ref=7.2.2"
#  vpc_name               = var.vpc_name
#  db_instance_class      = "db.t3.small"
#  team_name              = var.team_name
#  business_unit          = var.business_unit
#  application            = var.application
#  is_production          = var.is_production
#  namespace              = var.namespace
#  environment_name       = var.environment
#  infrastructure_support = var.infrastructure_support
#  db_engine              = "postgres"
#  db_engine_version      = "13"
#  rds_family             = "postgres13"
#
#  db_password_rotated_date = "14-02-2023"
#
#  providers = {
#    aws = aws.london
#  }
#}
#
#resource "aws_kms_key" "rds_s3_export" {
#  description             = "Used to encrypt the RDS export files in S3"
#  enable_key_rotation     = true
#  deletion_window_in_days = 20
#}
#
#module "rds_export" {
#  source = "../.."
#
#  cron_expression              = "49 16 * * ? *"
#  output_s3_bucket             = "serj-test-rds-export-1"
#  database_instance_identifier = aws_db_instance.test_db.identifier
#  kms_key_arn                  = aws_kms_key.rds_s3_export.arn
#
#  tags = local.tags
#}
