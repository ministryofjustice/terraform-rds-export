# EventBride rule to capture non-successful state function executions
resource "aws_cloudwatch_event_rule" "sfn_events" {
  name        = "${var.name}-${var.environment}-sfn-execution-status"
  role_arn    = aws_iam_role.eventbridge.arn #need to create this role
  description = "Capture the execution status of the state machine"

  event_pattern = jsonencode({
    source      = ["aws.states"],
    detail-type = ["Step Functions Execution Status Change"],
    detail = {
      status = ["FAILED", "TIMED_OUT", "ABORTED"]
      stateMachineArn = [
        aws_sfn_state_machine.db_restore.arn,
        aws_sfn_state_machine.db_export.arn,
        aws_sfn_state_machine.db_delete.arn
      ]
    }
  })
}

# Creating SNS for distributing messages
# Setting up the publish side
# Subscription side to be set outside of module
#trivy:ignore:AVD-AWS-0095 Topic not currently encrypted. TO INVESTIGATE IF REQUIRED.
resource "aws_sns_topic" "sfn_events" {
  #checkov:skip=CKV_AWS_26:Topic not currently encrypted. TO INVESTIGATE IF REQUIRED.
  name = "${var.name}-${var.environment}-sfn-events"
}

data "aws_iam_policy_document" "sns_topic_policy" {
  statement {
    effect  = "Allow"
    actions = ["sns:Publish"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    resources = [aws_sns_topic.sfn_events.arn]
  }
}

resource "aws_sns_topic_policy" "sfn_events" {
  arn    = aws_sns_topic.sfn_events.arn
  policy = data.aws_iam_policy_document.sns_topic_policy.json
}

# Events sent to SNS
resource "aws_cloudwatch_event_target" "sns" {
  rule      = aws_cloudwatch_event_rule.sfn_events.name
  arn       = aws_sns_topic.sfn_events.arn
  target_id = "SfnAlertToSNS"

  input_transformer {
    input_paths = {
      stateMachineArn = "$.detail.stateMachineArn"
      executionName   = "$.detail.name"
      status          = "$.detail.status"
      error           = "$.detail.error"
      cause           = "$.detail.cause"
      time            = "$.time"
    }

    input_template = <<EOF
    {
        "StateMachineARN": <stateMachineArn>,
        "ExecutionName": <executionName>,
        "Status": <status>,
        "Error": <error>,
        "Cause": <cause>,
        "Time": <time>
    }
    EOF
  }
}

# Creating CloudWatch resources
#trivy:ignore:AVD-AWS-0017 CloudWatch log groups encrypted by default.
resource "aws_cloudwatch_log_group" "eventbridge" {
  #checkov:skip=CKV_AWS_158:CloudWatch log groups encrypted by default.
  name = "${var.name}-${var.environment}-sfn-events-logs"

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

# Events sent to CloudWatch logs
resource "aws_cloudwatch_event_target" "cloudwatch" {
  rule = aws_cloudwatch_event_rule.sfn_events.name
  arn  = aws_cloudwatch_log_group.eventbridge.arn
}
