{
  "Comment": "Deletes the RDS DB Instance if it exists. Succeeds if the DB is deleted or already absent.",
  "StartAt": "Delete DB Instance",
  "States": {
    "Delete DB Instance": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:deleteDBInstance",
      "Parameters": {
        "DbInstanceIdentifier.$": "$.DbInstanceIdentifier",
        "SkipFinalSnapshot": true
      },
      "ResultSelector": {
        "DbInstanceIdentifier.$": "$.DbInstance.DbInstanceIdentifier",
        "DbInstanceArn.$": "$.DbInstance.DbInstanceArn",
        "DbInstanceStatus.$": "$.DbInstance.DbInstanceStatus",
        "Vpc.$": "$.DbInstance.DbSubnetGroup.VpcId"
      },
      "ResultPath": "$.DeleteDBInstance",
      "Next": "Wait For Delete DB Instance",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Success State",
          "ResultPath": "$.DeleteDBInstance"
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
        "DbInstanceIdentifier.$": "$.DbInstanceIdentifier"
      },
      "ResultSelector": {
        "DbInstanceStatus.$": "$.DbInstances[0].DbInstanceStatus",
        "DbInstanceIdentifier.$": "$.DbInstances[0].DbInstanceIdentifier",
        "DbInstanceArn.$": "$.DbInstances[0].DbInstanceArn"
      },
      "ResultPath": "$.DescribeDBDeleteResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Success State",
          "ResultPath": "$.DescribeDBDeleteResult"
        }
      ],
      "Next": "Choice End State"
    },
    "Choice End State": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.DescribeDBDeleteResult.DbInstanceStatus",
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