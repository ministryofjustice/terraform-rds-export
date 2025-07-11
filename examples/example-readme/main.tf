module "rds_export" {
  #checkov:skip=CKV_TF_1,CKV_TF_2: branch name ok for example. Use hash in production
  source = "github.com/ministryofjustice/terraform-rds-export?ref=initial-version"

  cron_expression              = "0 0 * * ? *" # Run every day at midnight
  output_s3_bucket             = "name-of-your-s3-bucket"
  database_instance_identifier = "name-of-your-rds-instance"
  kms_key_arn                  = "kms-key-arn"

  tags = {
    business-unit = "HMPPS"
    application   = "example"
    is-production = "false"
    owner         = "<team-name>: <team-email>"
  }
}
