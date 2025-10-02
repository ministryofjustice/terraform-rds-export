
module "module_test" {
  providers = {
    aws = aws
  }
  
  source           = "../../"

  name                  = "test"
  database_refresh_mode    = "test"
  db_name = "test"
  vpc_id                = "test"
  database_subnet_ids   = ["test"]
  kms_key_arn           = "test"
  master_user_secret_id = "test"
  environment              = "test"

  tags             = local.tags
}
