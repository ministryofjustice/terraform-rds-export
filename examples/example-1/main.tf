module "rds_export" {
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
