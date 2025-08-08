{
  "Comment": "Deletes the RDS DB Instance if it exists. Succeeds if the DB is deleted or already absent.",
  "StartAt": "Delete DB Instance",
  "States": {
    "Delete DB Instance": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:deleteDBInstance",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-sql-server-backup-export', $.name)",
        "SkipFinalSnapshot": true
      },
      "ResultPath": "$.DeleteDBInstance",
      "Next": "Wait For Delete DB Instance",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Success State",
          "ResultPath": null
        }
      ]
    },
    "Wait For Delete DB Instance": {
      "Type": "Wait",
      "Seconds": 180,
      "Next": "Describe DB Instance Deletion"
    },
    "Describe DB Instance Deletion": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:describeDBInstances",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-sql-server-backup-export', $.name)"
      },
      "ResultPath": "$.DescribeDBDeleteResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Success State",
          "ResultPath": null
        }
      ],
      "Next": "Choice End State"
    },
    "Choice End State": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.DescribeDBDeleteResult.DbInstances[0].DbInstanceStatus",
          "StringEquals": "deleting",
          "Next": "Wait For Delete DB Instance"
        }
      ],
      "Default": "Success State"
    },
    "Success State": {
      "Type": "Succeed"
    }
  },
  "TimeoutSeconds": 3600
}