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
  description     = "Lambda to check if all files have been uploaded to the S3 bucket"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 128
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = true
  docker_image    = "test-dms"

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.upload_checker_lambda_function.json

  environment_variables = {
    BACKUP_UPLOADS_BUCKET = aws_s3_bucket.backup_uploads.id
    STATE_MACHINE_ARN     = aws_sfn_state_machine.db_export.id
  }

  source_path = [{
    path = "${path.module}/lambda-functions/upload-checker/main.py"
    #pip_tmp_dir      = "${path.module}/lambda-functions/upload-checker/fixtures"
    #pip_requirements = "${path.module}/lambda-functions/upload-checker/requirements.txt"
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
      aws_db_instance.database.master_user_secret[0].secret_arn
    ]
  }
}

# Security group for database restore lambda function
resource "aws_security_group" "database_restore" {
  name        = "${var.name}-database-restore"
  description = "Allow outbound traffic from database restore lambda function"
  vpc_id      = var.vpc_id

  egress {
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
  memory_size     = 128
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = true
  docker_image    = "test-dms"

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  # TODO: 
  environment_variables = {
    UPLOADS_BUCKET      = aws_s3_bucket.backup_uploads.id
    DATABASE_SECRET_ARN = aws_db_instance.database.master_user_secret[0].secret_arn
    DATABASE_ENDPOINT   = aws_db_instance.database.address
  }

  source_path = [{
    path             = "${path.module}/lambda-functions/database-restore/main.py"
    pip_tmp_dir      = "${path.module}/lambda-functions/database-restore/fixtures"
    pip_requirements = "${path.module}/lambda-functions/database-restore/requirements.txt"
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
  memory_size     = 128
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = true
  docker_image    = "test-dms"

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  # TODO: 
  environment_variables = {
    DATABASE_SECRET_ARN = aws_db_instance.database.master_user_secret[0].secret_arn
    DATABASE_ENDPOINT   = aws_db_instance.database.address
  }

  source_path = [{
    path             = "${path.module}/lambda-functions/database-restore-status/main.py"
    pip_tmp_dir      = "${path.module}/lambda-functions/database-restore-status/fixtures"
    pip_requirements = "${path.module}/lambda-functions/database-restore-status/requirements.txt"
  }]

  tags = var.tags
}

module "database_export_scout" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-database-export-scout"
  description     = "Lambda to gather info for db export ${var.name}"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 128
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = true
  docker_image    = "test-dms"

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  # TODO: 
  environment_variables = {
    DATABASE_SECRET_ARN = aws_db_instance.database.master_user_secret[0].secret_arn
    DATABASE_ENDPOINT   = aws_db_instance.database.address
  }

  source_path = [{
    path             = "${path.module}/lambda-functions/database-export-scout/main.py"
    pip_tmp_dir      = "${path.module}/lambda-functions/database-export-scout/fixtures"
    pip_requirements = "${path.module}/lambda-functions/database-export-scout/requirements.txt"
  }]

  layers = [
    "arn:aws:lambda:eu-west-1:336392948345:layer:AWSSDKPandas-Python312:16"
  ]

  tags = var.tags
}

module "database_export" {
  # Commit hash for v7.20.1
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=84dfbfddf9483bc56afa0aff516177c03652f0c7"

  function_name   = "${var.name}-database-export-processor"
  description     = "Lambda to export data for ${var.name}"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 128
  timeout         = 10
  architectures   = ["x86_64"]
  build_in_docker = true
  docker_image    = "test-dms"

  # VPC Config - Lambda function needs to be in the same VPC as the RDS instance
  vpc_subnet_ids         = var.database_subnet_ids
  vpc_security_group_ids = [aws_security_group.database_restore.id]
  attach_network_policy  = true

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.data_restore_lambda_function.json

  # TODO: 
  environment_variables = {
    DATABASE_SECRET_ARN = aws_db_instance.database.master_user_secret[0].secret_arn
    DATABASE_ENDPOINT   = aws_db_instance.database.address
  }

  source_path = [{
    path             = "${path.module}/lambda-functions/database-export/main.py"
    pip_tmp_dir      = "${path.module}/lambda-functions/database-export/fixtures"
    pip_requirements = "${path.module}/lambda-functions/database-export/requirements.txt"
  }]

  layers = [
    "arn:aws:lambda:eu-west-1:336392948345:layer:AWSSDKPandas-Python312:16"
  ]

  tags = var.tags
}
