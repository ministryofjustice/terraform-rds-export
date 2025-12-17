resource "aws_iam_role" "state_machine" {
  #checkov:skip=CKV_AWS_61:See comment below
  name = "${var.name}-${var.environment}-step-functions-database-export"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "state_machine" {
  #checkov:skip=CKV_AWS_288,CKV_AWS_290,CKV_AWS_286,CKV_AWS_287,CKV_AWS_63,CKV_AWS_289,CKV_AWS_61,CKV_AWS_355:Look at comment above
  #checkov:skip=CKV_AWS_62:See comment above
  name = "${var.name}-${var.environment}-step-functions-database-export"
  role = aws_iam_role.state_machine.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds:CreateDBInstance",
          "rds:DescribeDBInstances",
          "rds:DeleteDBInstance"
        ]
        Resource = [
          "arn:aws:rds:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:db:${var.name}-${var.environment}-sql-server-backup-export",
          aws_security_group.database.arn,
          aws_db_subnet_group.database.arn,
          aws_db_parameter_group.database.arn,
          aws_db_option_group.database.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = concat(
          [
            module.database_restore.lambda_function_arn,
            module.database_restore_status.lambda_function_arn,
            module.database_export_scanner.lambda_function_arn,
            module.database_export_processor.lambda_function_arn,
            module.export_validation_rowcount_updater.lambda_function_arn,
            module.transform_output.lambda_function_arn
          ],
          var.get_views ? [module.database_views_scanner[0].lambda_function_arn] : []
        )
      },
      {
        Effect = "Allow",
        Action = [
          "events:PutRule",
          "events:PutTargets",
          "events:TagResource",
          "events:DescribeRule"
        ],
        Resource = [
          "arn:aws:events:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForStepFunctionsExecutionRule"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "events:PutEvents"
        ],
        Resource = [
          "arn:aws:events:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:event-bus/default"
        ]
      }
    ]
  })
}

resource "aws_iam_policy" "allow_start_execution" {
  name = "AllowStartExportStateMachine-${var.name}-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "states:StartExecution",
          "states:DescribeStateMachine",
          "states:ListExecutions"
        ],
        Resource = concat(
          [
            "arn:aws:states:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name}-${var.environment}-database-export",
            "arn:aws:states:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name}-${var.environment}-database-delete"
          ],
          var.get_views ? ["arn:aws:states:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name}-${var.environment}-database-export-views"] : []
        )
      },
      {
        Effect = "Allow",
        Action = [
          "states:DescribeExecution",
        ],
        Resource = concat(
          [
            "arn:aws:states:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:execution:${var.name}-${var.environment}-database-export",
            "arn:aws:states:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:execution:${var.name}-${var.environment}-database-delete"
          ],
          var.get_views ? ["arn:aws:states:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:execution:${var.name}-${var.environment}-database-export-views"] : []
        )
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_start_export" {
  role       = aws_iam_role.state_machine.name
  policy_arn = aws_iam_policy.allow_start_execution.arn
}

resource "aws_iam_role" "database_restore" {
  #checkov:skip=CKV_AWS_61:See comment below
  name = "${var.name}-${var.environment}-rds-restore"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "database_restore" {
  name = "${var.name}-${var.environment}-rds-restore"
  role = aws_iam_role.database_restore.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:ReEncrypt*",
          "kms:DescribeKey"
        ]
        Resource = [
          var.kms_key_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket",
          "s3:GetObject",
          "s3:GetObjectAttributes",
          "s3:PutObject",
          "s3:ListMultipartUploadParts",
          "s3:AbortMultipartUpload",
        ]
        Resource = [
          module.s3-bucket-backup-uploads.bucket.arn,
          "${module.s3-bucket-backup-uploads.bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:GetBucketLocation",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          module.s3-bucket-parquet-exports.bucket.arn,
          "${module.s3-bucket-parquet-exports.bucket.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role" "eventbridge" {
  name = "${var.name}-${var.environment}-eventbridge"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "events.amazonaws.com"
        },
        "Action" : "sts:AssumeRole",
        "Condition" : {
          "StringEquals" : {
            "aws:SourceAccount" : data.aws_caller_identity.current.id
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_cloudwatch_publish" {
  name = "${var.name}-${var.environment}-cloudwatch-publish"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogStream"
        ]
        Resource = "${aws_cloudwatch_log_group.eventbridge.arn}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_sns_publish" {
  name = "${var.name}-${var.environment}-sns-publish"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "sns:Publish"
        Resource = aws_sns_topic.sfn_events.arn
      }
    ]
  })
}
