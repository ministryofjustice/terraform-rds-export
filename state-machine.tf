resource "aws_sfn_state_machine" "db_restore" {
  # checkov:skip=CKV_AWS_284: x-ray tracing not required for now
  # checkov:skip=CKV_AWS_285: Logging not required for now. TODO: Add this in the future
  name     = "${var.name}-${var.environment}-database-restore"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-restore.asl.json.tpl", {
    DatabaseRestoreLambdaArn       = module.database_restore.lambda_function_arn
    DatabaseRestoreStatusLambdaArn = module.database_restore_status.lambda_function_arn
    MasterUserPassword             = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName             = resource.aws_db_parameter_group.database.name
    OptionGroupName                = resource.aws_db_option_group.database.name
    VpcSecurityGroupIds            = [resource.aws_security_group.database.id]
    DbSubnetGroupName              = resource.aws_db_subnet_group.database.name
    DatabaseExportStateMachineArn  = resource.aws_sfn_state_machine.db_export.arn
  })
}

resource "aws_sfn_state_machine" "db_export" {
  # checkov:skip=CKV_AWS_284: x-ray tracing not required for now
  # checkov:skip=CKV_AWS_285: Logging not required for now. TODO: Add this in the future
  name     = "${var.name}-${var.environment}-database-export"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-export.asl.json.tpl", {
    DatabaseExportScannerLambdaArn   = module.database_export_scanner.lambda_function_arn
    DatabaseExportProcessorLambdaArn = module.database_export_processor.lambda_function_arn
    MasterUserPassword               = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName               = resource.aws_db_parameter_group.database.name
    OptionGroupName                  = resource.aws_db_option_group.database.name
    VpcSecurityGroupIds              = [resource.aws_security_group.database.id]
    DbSubnetGroupName                = resource.aws_db_subnet_group.database.name
    DatabaseDeleteStateMachineArn    = resource.aws_sfn_state_machine.db_delete.arn
    max_concurrency                  = var.max_concurrency
  })
}

resource "aws_sfn_state_machine" "db_delete" {
  # checkov:skip=CKV_AWS_284: x-ray tracing not required for now
  # checkov:skip=CKV_AWS_285: Logging not required for now. TODO: Add this in the future
  name     = "${var.name}-${var.environment}-database-delete"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-delete.asl.json.tpl", {
    MasterUserPassword  = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName  = resource.aws_db_parameter_group.database.name
    OptionGroupName     = resource.aws_db_option_group.database.name
    VpcSecurityGroupIds = [resource.aws_security_group.database.id]
    DbSubnetGroupName   = resource.aws_db_subnet_group.database.name
  })
}