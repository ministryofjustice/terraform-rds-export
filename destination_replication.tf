
# Grants the source account's replication role permission to replicate
# objects into the parquet exports bucket so it can act as a batch
# replication destination.
data "aws_iam_policy_document" "batch_replication_destination" {

  statement {
    sid    = "AllowReplicationFromSourceRole"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.batch_replication_source_role_arn]
    }

    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ReplicateTags",
      "s3:ObjectOwnerOverrideToBucketOwner"
    ]

    resources = [
      "${module.s3-bucket-parquet-exports.bucket.arn}/*"
    ]
  }

  statement {
    sid    = "AllowReplicationBucketPermissions"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.batch_replication_source_role_arn]
    }

    actions = [
      "s3:GetBucketVersioning",
      "s3:PutBucketVersioning"
    ]

    resources = [
      module.s3-bucket-parquet-exports.bucket.arn
    ]
  }
}

resource "aws_s3_bucket_policy" "batch_replication_destination" {

  bucket = module.s3-bucket-parquet-exports.bucket.id
  policy = data.aws_iam_policy_document.batch_replication_destination.json
}
