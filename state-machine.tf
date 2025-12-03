# Creates RDS DB Instance and restores the .bak file
resource "aws_sfn_state_machine" "db_restore" {
  #checkov:skip=CKV_AWS_284:X-ray tracing not required for now
  #checkov:skip=CKV_AWS_285:Logging not required for now. Execution history recorded in Step Function.
  name     = "${var.name}-${var.environment}-database-restore"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-restore.asl.json.tpl", {
    DatabaseRestoreLambdaArn       = module.database_restore.lambda_function_arn
    DatabaseRestoreStatusLambdaArn = module.database_restore_status.lambda_function_arn
    MasterUserPassword             = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName             = aws_db_parameter_group.database.name
    OptionGroupName                = aws_db_option_group.database.name
    VpcSecurityGroupIds            = [aws_security_group.database.id]
    DbSubnetGroupName              = aws_db_subnet_group.database.name
    DatabaseExportStateMachineArn  = aws_sfn_state_machine.db_export.arn
    Engine                         = "sqlserver-se"
    EngineVersion                  = var.engine_version
  })
}

# Scans the data, creates metadata in Glue Catalog, exports the data to S3 and row count table
resource "aws_sfn_state_machine" "db_export" {
  #checkov:skip=CKV_AWS_284:x-ray tracing not required for now
  #checkov:skip=CKV_AWS_285:Logging not required for now. Execution history recorded in Step Function.
  name     = "${var.name}-${var.environment}-database-export"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-export.asl.json.tpl", {
    DatabaseExportScannerLambdaArn           = module.database_export_scanner.lambda_function_arn
    DatabaseExportProcessorLambdaArn         = module.database_export_processor.lambda_function_arn
    ExportValidationRowCountUpdaterLambdaArn = module.export_validation_rowcount_updater.lambda_function_arn
    TransformOutputLambdaArn                 = module.transform_output.lambda_function_arn
    MasterUserPassword                       = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName                       = aws_db_parameter_group.database.name
    OptionGroupName                          = aws_db_option_group.database.name
    VpcSecurityGroupIds                      = [aws_security_group.database.id]
    DbSubnetGroupName                        = aws_db_subnet_group.database.name
    LambdaArn                                = var.get_views ? aws_sfn_state_machine.db_export_views[0].arn : aws_sfn_state_machine.db_delete.arn
    max_concurrency                          = var.max_concurrency

  })
}

# Gets view definitions and data
resource "aws_sfn_state_machine" "db_export_views" {
  #checkov:skip=CKV_AWS_284:x-ray tracing not required for now
  #checkov:skip=CKV_AWS_285:Logging not required for now. Execution history recorded in Step Function.
  count = var.get_views ? 1 : 0

  name     = "${var.name}-${var.environment}-database-export-views"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-export-views.asl.json.tpl", {
    DatabaseViewsScannerLambdaArn   = module.database_views_scanner.lambda_function_arn
    DatabaseViewsProcessorLambdaArn = module.database_views_processor.lambda_function_arn
    TransformOutputLambdaArn        = module.transform_output.lambda_function_arn
    MasterUserPassword              = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName              = aws_db_parameter_group.database.name
    OptionGroupName                 = aws_db_option_group.database.name
    VpcSecurityGroupIds             = [aws_security_group.database.id]
    DbSubnetGroupName               = aws_db_subnet_group.database.name
    DatabaseDeleteStateMachineArn   = aws_sfn_state_machine.db_delete.arn
    max_concurrency                 = var.max_concurrency
  })
}

# Deletes the RDS DB Instance
resource "aws_sfn_state_machine" "db_delete" {
  #checkov:skip=CKV_AWS_284:x-ray tracing not required for now
  #checkov:skip=CKV_AWS_285:Logging not required for now. Execution history recorded in Step Function.
  name     = "${var.name}-${var.environment}-database-delete"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/db-delete.asl.json.tpl", {
    MasterUserPassword  = data.aws_secretsmanager_secret_version.master_user_secret.secret_string
    ParameterGroupName  = aws_db_parameter_group.database.name
    OptionGroupName     = aws_db_option_group.database.name
    VpcSecurityGroupIds = [aws_security_group.database.id]
    DbSubnetGroupName   = aws_db_subnet_group.database.name
  })
}
