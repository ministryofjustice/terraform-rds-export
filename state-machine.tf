resource "aws_sfn_state_machine" "db_export" {
  # checkov:skip=CKV_AWS_284: x-ray tracing not required for now
  # checkov:skip=CKV_AWS_285: Logging not required for now. TODO: Add this in the future
  name     = "${var.name}-export"
  role_arn = aws_iam_role.state_machine.arn

  definition = templatefile("${path.module}/statemachine.asl.json.tpl", {
    DatabaseRestoreLambdaArn         = module.database_restore.lambda_function_arn
    DatabaseRestoreStatusLambdaArn   = module.database_restore_status.lambda_function_arn
    DatabaseExportScannerLambdaArn   = module.database_export_scanner.lambda_function_arn
    DatabaseExportProcessorLambdaArn = module.database_export_processor.lambda_function_arn
  })
}
