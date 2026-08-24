resource "aws_iam_role" "migration_replication" {
  count = local.migration_replication_create ? 1 : 0

  name = "${var.name}-parquet-exports-replication-${var.environment}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = [
            "s3.amazonaws.com",
            "batchoperations.s3.amazonaws.com"
          ]
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_s3_bucket" "batch_manifest" {
  count = local.migration_replication_create ? 1 : 0

  bucket_prefix = "${var.name}-parquet-exports-batch-manifest-${var.environment}-"

  tags = var.tags
}

resource "aws_iam_policy" "migration_replication" {
  count = local.migration_replication_create ? 1 : 0

  name = "${var.name}-parquet-exports-replication-IAM-${var.environment}-policy"

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "SourceBucketPermissions"
        Effect = "Allow"

        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket",
          "s3:PutInventoryConfiguration"
        ]

        Resource = [
          module.s3-bucket-parquet-exports.bucket.arn
        ]
      },
      {
        Sid    = "SourceObjectPermissions"
        Effect = "Allow"

        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging",
          "s3:InitiateReplication"
        ]

        Resource = [
          "${module.s3-bucket-parquet-exports.bucket.arn}/*"
        ]
      },
      {
        Sid    = "DestinationPermissions"
        Effect = "Allow"

        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete",
          "s3:ReplicateTags"
        ]

        Resource = [
          "${var.migration_replication_destination_arn}/*"
        ]
      },
      {
        Sid    = "ManifestAndReportPermissions"
        Effect = "Allow"

        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject"
        ]

        Resource = [
          "${aws_s3_bucket.batch_manifest[0].arn}/*"
        ]
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "migration_replication" {
  count = local.migration_replication_create ? 1 : 0

  role       = aws_iam_role.migration_replication[0].name
  policy_arn = aws_iam_policy.migration_replication[0].arn
}

resource "aws_s3_bucket_replication_configuration" "migration_replication" {
  count = local.migration_replication_create ? 1 : 0

  bucket = module.s3-bucket-parquet-exports.bucket.id
  role   = aws_iam_role.migration_replication[0].arn

  rule {
    id     = "migration-replication"
    status = var.migration_replication_rule_enabled ? "Enabled" : "Disabled"

    filter {
      prefix = ""
    }

    destination {
      bucket = var.migration_replication_destination_arn
    }

    delete_marker_replication {
      status = "Disabled"
    }
  }

  depends_on = [aws_iam_role_policy_attachment.migration_replication]
}

data "aws_iam_policy_document" "migration_replication_trigger_lambda_function" {
  count = local.migration_replication_create ? 1 : 0

  statement {
    actions = [
      "s3:CreateJob",
      "s3:DescribeJob",
      "s3:UpdateJobStatus",
      "s3:ListJobs"
    ]

    resources = ["*"]
  }

  statement {
    actions = [
      "iam:PassRole"
    ]

    resources = [
      aws_iam_role.migration_replication[0].arn
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["batchoperations.s3.amazonaws.com"]
    }
  }

  statement {
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket"
    ]

    resources = [
      module.s3-bucket-parquet-exports.bucket.arn,
      aws_s3_bucket.batch_manifest[0].arn
    ]
  }

  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]

    resources = [
      "${module.s3-bucket-parquet-exports.bucket.arn}/*",
      "${aws_s3_bucket.batch_manifest[0].arn}/*"
    ]
  }
}

#trivy:ignore:AVD-AWS-0066 X-Ray tracing not currently required. Logs sent to CloudWatch.
module "migration_replication_trigger" {
  count = local.migration_replication_create ? 1 : 0

  # Commit hash for v8.1.2
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda?ref=a7db1252f2c2048ab9a61254869eea061eae1318"

  function_name   = "${var.name}-${var.environment}-migration-replication-trigger"
  description     = "Lambda to trigger S3 Batch Replication"
  handler         = "main.handler"
  runtime         = "python3.12"
  memory_size     = 512
  timeout         = 300
  architectures   = ["x86_64"]
  build_in_docker = false

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.migration_replication_trigger_lambda_function[0].json

  environment_variables = {
    ACCOUNT_ID             = data.aws_caller_identity.current.account_id
    REPLICATION_ROLE_ARN   = aws_iam_role.migration_replication[0].arn
    SOURCE_BUCKET_ARN      = module.s3-bucket-parquet-exports.bucket.arn
    DESTINATION_BUCKET_ARN = var.migration_replication_destination_arn
    MANIFEST_BUCKET_ARN    = aws_s3_bucket.batch_manifest[0].arn
    CUTOFF_DATE            = coalesce(var.migration_replication_cutoff_date, "")
  }

  source_path = [{
    path = "${path.module}/lambda_functions/migration_replication_trigger/main.py"
  }]

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "migration_replication_trigger" {
  count = local.migration_replication_create && var.migration_replication_trigger_schedule_expression != null ? 1 : 0

  name                = "${var.name}-${var.environment}-migration-replication-trigger"
  description         = "Schedule for migration replication trigger lambda"
  schedule_expression = var.migration_replication_trigger_schedule_expression
}

resource "aws_cloudwatch_event_target" "migration_replication_trigger" {
  count = local.migration_replication_create && var.migration_replication_trigger_schedule_expression != null ? 1 : 0

  rule      = aws_cloudwatch_event_rule.migration_replication_trigger[0].name
  target_id = "lambda"
  arn       = module.migration_replication_trigger[0].lambda_function_arn
}

resource "aws_lambda_permission" "migration_replication_trigger" {
  count = local.migration_replication_create && var.migration_replication_trigger_schedule_expression != null ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.migration_replication_trigger[0].lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.migration_replication_trigger[0].arn
}