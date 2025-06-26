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

resource "aws_iam_role" "database_restore" {
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

// Update this role policy to allow usage of a kms key by the rds s3 export task and to allow the export task to write to the s3 bucket
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
