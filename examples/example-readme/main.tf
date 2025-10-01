terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  required_version = "~> 1.5"
}

module "rds_export" {
  #checkov:skip=CKV_TF_1,CKV_TF_2: Use commit hash in production
  source = "github.com/ministryofjustice/terraform-rds-export?ref=<commit-hash>"

  providers = {
    aws = aws
  }

  name                  = "ppud"
  database_refresh_mode    = "incremental"
  db_name = "ppud_dev"
  vpc_id                = "vpc-01234567890abcdef"
  database_subnet_ids   = ["subnet-1234abcd", "subnet-5678efgh", "subnet-9012ijkl"]
  kms_key_arn           = "arn:aws:kms:us-east-1:111122223333:key/abcd1234-5678-90ab-cdef-EXAMPLEKEY"
  master_user_secret_id = "arn:aws:secretsmanager:us-east-1:111122223333:secret:my-secret-1234abcd"
  environment              = var.tags["environment"]

tags = {
  business-unit    = "HMPPS"
  application      = "Data Engineering"
  environment-name = "dev"
  is-production    = "False"
  owner            = "Data Engineering: DataEngineering-gg@justice.gov.uk"
  source-code      = "https://github.com/ministryofjustice/analytical-platform/tree/main/terraform/aws/analytical-platform-data-engineering-production/ppud-dev"
}
}
