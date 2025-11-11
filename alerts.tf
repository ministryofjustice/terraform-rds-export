resource "aws_cloudwatch_event_rule" "sfn_events" {
    name = "${var.name}_${var.environment}_sfn_execution_status"
    role_arn    = aws_iam_role.eventbridge.arn #need to create this role
    description = "Capture the execution status of the state machine"

    event_pattern = jsonencode({
        source = ["aws.states"],
        detail-type = ["Step Functions Execution Status Change"],
        detail = {
            status = ["FAILED", "TIMED_OUT", "ABORTED"]
            stateMachineArn = [
                "${aws_sfn_state_machine.db_restore.arn}",
                "${aws_sfn_state_machine.db_export.arn}",
                "${aws_sfn_state_machine.db_delete.arn}"
            ]
        }
    })
}

resource "aws_cloudwatch_log_group" "eventbridge" {
  name = "${var.name}_${var.environment}_events_logs"

  log_group_class   = "STANDARD"
  retention_in_days = 0
  tags              = var.tags
}

data "aws_iam_policy_document" "eventbridge" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    principals {
      type = "Service"
      identifiers = [
        "events.amazonaws.com",
        "delivery.logs.amazonaws.com"
      ]
    }
    resources = [
      "arn:aws:logs:${data.aws_region.current.id}:${data.aws_caller_identity.current.id}:log-group:${aws_cloudwatch_log_group.eventbridge.name}:*"
    ]
  }
}

resource "aws_cloudwatch_log_resource_policy" "eventbridge" {
  policy_document = data.aws_iam_policy_document.eventbridge.json
  policy_name     = "eventbridge-log-publishing-policy-${var.name}-${var.environment}"
}

resource "aws_cloudwatch_event_target" "cloudwatch" {
    rule = aws_cloudwatch_event_rule.sfn_events.name
    arn = aws_cloudwatch_log_group.eventbridge.arn
}