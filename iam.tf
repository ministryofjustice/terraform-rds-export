#resource "aws_iam_role" "eventbridge_sfn" {
#  name = "${var.database_instance_identifier}-rds-s3-export"
#
#  assume_role_policy = jsonencode({
#    Version = "2012-10-17"
#    Statement = [
#      {
#        Action = "sts:AssumeRole"
#        Effect = "Allow"
#        Principal = {
#          Service = "events.amazonaws.com"
#        }
#      }
#    ]
#  })
#}
#
#resource "aws_iam_role_policy" "eventbridge_sfn" {
#  name = "eventbridge-sfn-execution"
#  role = aws_iam_role.eventbridge_sfn.id
#
#  policy = jsonencode({
#    Version = "2012-10-17"
#    Statement = [
#      {
#        Effect = "Allow"
#        Action = [
#          "states:StartExecution"
#        ]
#        Resource = [
#          aws_sfn_state_machine.rds_export_tracker.arn
#        ]
#      }
#    ]
#  })
#}

resource "aws_iam_role" "state_machine" {
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
  name = "${var.name}-step-functions-database-export"
  role = aws_iam_role.state_machine.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["*"]
        Resource = ["*"]
      },
      # Allow state machine to trigger DB Restore lambda function
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          module.database_restore.lambda_function_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role" "database_export" {
  name = "${var.name}-database-export"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "export.rds.amazonaws.com"
        }
      }
    ]
  })
}

// Update this role policy to allow usage of a kms key by the rds s3 export task and to allow the export task to write to the s3 bucket
resource "aws_iam_role_policy" "database_export" {
  name = "${var.name}-rds-export"
  role = aws_iam_role.database_export.name

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

# Role for RDS to assume to export to S3
resource "aws_iam_role" "rds_export" {
  name = "${var.name}-rds-export"

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

resource "aws_iam_role_policy" "rds_export" {
  name = "${var.name}-rds-export"
  role = aws_iam_role.rds_export.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [
          aws_s3_bucket.backup_uploads.arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectAttributes",
          "s3:PutObject",
          "s3:ListMultipartUploadParts",
          "s3:AbortMultipartUpload",
        ]
        Resource = [
          "${aws_s3_bucket.backup_uploads.arn}/*",
        ]
      }
    ]
  })
}
