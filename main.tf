resource "aws_cloudwatch_event_rule" "export_schedule" {
  name                = "${var.database_instance_identifier}-export-schedule"
  description         = "Triggers RDS snapshot export task"
  schedule_expression = "cron(${var.cron_expression})"
}

resource "aws_cloudwatch_event_target" "export_task" {
  rule      = aws_cloudwatch_event_rule.export_schedule.name
  target_id = "RDSSnapshotExportTask"
  arn       = aws_sfn_state_machine.rds_export_tracker.arn
  role_arn  = aws_iam_role.eventbridge_sfn.arn

  input = jsonencode({
    #ExportTaskIdentifier = "export-${var.database_id}-${formatdate("YYYY-MM-DD-HH-mm", timestamp())}"
    ExportTaskIdentifier = "export-${var.database_instance_identifier}"
    DBInstanceIdentifier = var.database_instance_identifier
    S3BucketName         = var.output_s3_bucket
    IamRoleArn           = aws_iam_role.rds_export.arn
    KmsKeyId             = var.kms_key_arn
  })
}

resource "aws_sfn_state_machine" "rds_export_tracker" {
  name     = "${var.database_instance_identifier}-export"
  role_arn = aws_iam_role.state_machine.arn

  definition = file("${path.module}/statemachine.asl.json")
}
