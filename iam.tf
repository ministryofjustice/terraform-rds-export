resource "aws_iam_role" "state_machine" {
  # checkov:skip=CKV_AWS_61: See comment below
  name = "${var.name}-step-functions-database-export"

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
  # checkov:skip=CKV_AWS_288,CKV_AWS_290,CKV_AWS_286,CKV_AWS_287,CKV_AWS_63,CKV_AWS_289,CKV_AWS_61,CKV_AWS_355: Look at comment above
  # checkov:skip=CKV_AWS_62: See comment above
  name = "${var.name}-step-functions-database-export"
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
          "arn:aws:rds:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:db:${var.name}-sql-server-backup-export",
          "${aws_security_group.database.arn}",
          "${aws_db_subnet_group.database.arn}",
          "${aws_db_parameter_group.database.arn}",
          "${aws_db_option_group.database.arn}"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          module.database_restore.lambda_function_arn,
          module.database_restore_status.lambda_function_arn,
          module.database_export_scanner.lambda_function_arn,
          module.database_export_processor.lambda_function_arn
        ]
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
          "arn:aws:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForStepFunctionsExecutionRule"
        ]
      }
    ]
  })
}

resource "aws_iam_policy" "allow_start_execution" {
  name = "AllowStartExportStateMachine-${var.name}"

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
        Resource = [
          "arn:aws:states:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name}-database-export",
          "arn:aws:states:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name}-database-delete"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "states:DescribeExecution",
        ],
        Resource = [
          "arn:aws:states:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:execution:${var.name}-database-export",
          "arn:aws:states:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:execution:${var.name}-database-delete"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_start_export" {
  role       = aws_iam_role.state_machine.name
  policy_arn = aws_iam_policy.allow_start_execution.arn
}

resource "aws_iam_role" "database_restore" {
  # checkov:skip=CKV_AWS_61: See comment below
  name = "${var.name}-rds-restore"

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
  name = "${var.name}-rds-restore"
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
          "${aws_s3_bucket.backup_uploads.arn}",
          "${aws_s3_bucket.backup_uploads.arn}/*"
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
          aws_s3_bucket.parquet_exports.arn,
          "${aws_s3_bucket.parquet_exports.arn}/*"
        ]
      }
    ]
  })
}
