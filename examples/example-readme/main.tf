module "rds_export" {
  #checkov:skip=CKV_TF_1,CKV_TF_2: branch name ok for example. Use hash in production
  source = "github.com/ministryofjustice/terraform-rds-export?ref=initial-version"

  name                  = "name-of-your-rds-database"
  vpc_id                = "vpc-arn"
  database_subnet_ids   = "vpc-subnet-ids"
  kms_key_arn           = "kms-key-arn"
  master_user_secret_id = "secret-arn-containing-master-user-password"

  tags = {
    business-unit = "HMPPS"
    application   = "example"
    is-production = "false"
    owner         = "<team-name>: <team-email>"
  }
}
