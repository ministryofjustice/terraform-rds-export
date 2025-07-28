data "aws_iam_policy_document" "upload_checker_lambda_function" {
  statement {
    // Allow the lambda to read the upload files from the S3 bucket
    actions = [
      "s3:ListBucket",
      "s3:GetObject"
    ]

    resources = [
      aws_s3_bucket.backup_uploads.arn,
      "${aws_s3_bucket.backup_uploads.arn}/*",
    ]
  }

  // Allow the lambda to start the state machine
  statement {
    actions = [
      "states:StartExecution"
    ]

    resources = [
      aws_sfn_state_machine.db_export.arn
    ]
  }
}

module "upload_checker" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-upload-checker"
  description     = "Lambda to check if a file have been uploaded to the S3 bucket"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 1024
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = false

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.upload_checker_lambda_function.json

  environment_variables = {
    BACKUP_UPLOADS_BUCKET = aws_s3_bucket.backup_uploads.id
    STATE_MACHINE_ARN     = aws_sfn_state_machine.db_export.id
    OUTPUT_BUCKET         = aws_s3_bucket.parquet_exports.id
    NAME                  = var.name
  }

  source_path = [{
    path = "${path.module}/lambda-functions/upload-checker/main.py"
  }]

  tags = var.tags
}

# IAM policy document for the database restore lambda function - allow get secret value for db password
data "aws_iam_policy_document" "data_restore_lambda_function" {
  statement {
    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      data.aws_secretsmanager_secret_version.master_user_secret.arn
    ]
  }

  statement {
    actions = [
      "kms:Encrypt*",
      "kms:Decrypt*",
      "kms:GenerateDataKey*",
      "kms:Describe*"
    ]

    resources = [
      "${var.kms_key_arn}"
    ]
  }

  statement {
    actions = [
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.parquet_exports.arn}/*",
    ]
  }

  statement {
    actions = [
      "glue:*"
    ]

    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/*",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/*/*"
    ]
  }
}

# Security group for database restore lambda function
#trivy:ignore:AVD-AWS-0104
resource "aws_security_group" "database_restore" {
  name        = "${var.name}-database-restore"
  description = "Allow outbound traffic from database restore lambda function"
  vpc_id      = var.vpc_id

  # checkov:skip=CKV_AWS_382: Outbound traffic is required for the lambda to access the database and S3 bucket
  egress {
    description = "Allow all outbound traffic from database restore lambda function"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "database_restore" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-database-restore"
  description     = "Lambda to restore the database from the backup files in the S3 bucket"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 1024
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = false

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  environment_variables = {
    UPLOADS_BUCKET         = aws_s3_bucket.backup_uploads.id
    DATABASE_PW_SECRET_ARN = data.aws_secretsmanager_secret_version.master_user_secret.arn
  }

  source_path = [{
    path = "${path.module}/lambda-functions/database-restore/"
    commands = [
      "pip3.12 install --platform=manylinux2014_x86_64 --only-binary=:all: --no-compile --target=. -r requirements.txt",
      ":zip",
    ]
  }]

  tags = var.tags
}

module "database_restore_status" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-database-restore-status"
  description     = "Lambda to check the status of the database restore from S3"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 1024
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = false

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  environment_variables = {
    DATABASE_PW_SECRET_ARN = data.aws_secretsmanager_secret_version.master_user_secret.arn
  }

  source_path = [{
    path = "${path.module}/lambda-functions/database-restore-status/"
    commands = [
      "pip3.12 install --platform=manylinux2014_x86_64 --only-binary=:all: --no-compile --target=. -r requirements.txt",
      ":zip",
    ]
  }]

  tags = var.tags
}

module "database_export_scanner" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-database-export-scanner"
  description     = "Lambda to gather info for db export ${var.name}"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 2048
  timeout         = 300
  architectures   = ["x86_64"]
  build_in_docker = false

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  environment_variables = {
    DATABASE_PW_SECRET_ARN = data.aws_secretsmanager_secret_version.master_user_secret.arn
  }

  source_path = [{
    path = "${path.module}/lambda-functions/database-export-scanner/"
    commands = [
      "pip3.12 install --platform=manylinux2014_x86_64 --only-binary=:all: --no-compile --target=. -r requirements.txt",
      ":zip",
    ]
  }]

  layers = [
    "arn:aws:lambda:${data.aws_region.current.name}:336392948345:layer:AWSSDKPandas-Python312:18"
  ]

  tags = var.tags
}

module "database_export_processor" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-database-export-processor"
  description     = "Lambda to export data for ${var.name}"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 2048
  timeout         = 300
  architectures   = ["x86_64"]
  build_in_docker = false

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  environment_variables = {
    DATABASE_PW_SECRET_ARN = data.aws_secretsmanager_secret_version.master_user_secret.arn
    OUTPUT_BUCKET          = aws_s3_bucket.parquet_exports.id
  }

  source_path = [{
    path = "${path.module}/lambda-functions/database-export/"
    commands = [
      "pip3.12 install --platform=manylinux2014_x86_64 --only-binary=:all: --no-compile --target=. -r requirements.txt",
      ":zip",
    ]
  }]

  layers = [
    "arn:aws:lambda:${data.aws_region.current.name}:336392948345:layer:AWSSDKPandas-Python312:18"
  ]

  tags = var.tags
}
