{
  "Comment": "Exports the latest RDS snapshot to S3, creating a new one if necessary",
  "StartAt": "RunDatabaseRestoreLambda",
  "States": {
    "RunDatabaseRestoreLambda": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:eu-west-1:684969100054:function:dmet-sql-server-database-restore",
      "ResultPath": "$.DatabaseRestoreLambdaResult",
      "Next": "Run Restore Status Check"
    },
    "Run Restore Status Check": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:eu-west-1:684969100054:function:dmet-sql-server-database-restore-status:$LATEST",
        "Payload": {
          "task_id.$": "$.DatabaseRestoreLambdaResult.task_id",
          "db_name.$": "$.DatabaseRestoreLambdaResult.db_name"
        }
      },
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 1,
          "MaxAttempts": 3,
          "BackoffRate": 2,
          "JitterStrategy": "FULL"
        }
      ],
      "Next": "Choice",
      "ResultPath": "$.DatabaseRestoreStatusLambdaResult"
    },
    "Choice": {
      "Type": "Choice",
      "Choices": [
        {
          "Not": {
            "Variable": "$.DatabaseRestoreStatusLambdaResult.Payload.restore_status",
            "StringEquals": "SUCCESS"
          },
          "Next": "Wait For Restore Completion"
        }
      ],
      "Default": "CreateNewSnapshot"
    },
    "Wait For Restore Completion": {
      "Type": "Wait",
      "Seconds": 10,
      "Next": "Run Restore Status Check"
    },
    "CreateNewSnapshot": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:createDBSnapshot",
      "Parameters": {
        "DbInstanceIdentifier.$": "$.DatabaseRestoreLambdaResult.db_identifier",
        "DbSnapshotIdentifier.$": "$.DatabaseRestoreLambdaResult.db_name"
      },
      "ResultPath": "$.snapshotResult",
      "Next": "WaitForSnapshotCompletion"
    },
    "WaitForSnapshotCompletion": {
      "Type": "Wait",
      "Seconds": 60,
      "Next": "CheckSnapshotStatus"
    },
    "CheckSnapshotStatus": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:describeDBSnapshots",
      "Parameters": {
        "DbSnapshotIdentifier.$": "$.snapshotResult.DbSnapshot.DbSnapshotIdentifier"
      },
      "ResultPath": "$.snapshotStatus",
      "Next": "EvaluateSnapshotStatus"
    },
    "EvaluateSnapshotStatus": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.snapshotStatus.DbSnapshots[0].Status",
          "StringEquals": "available",
          "Next": "StartExportTask"
        }
      ],
      "Default": "WaitForSnapshotCompletion"
    },
    "StartExportTask": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:startExportTask",
      "Parameters": {
        "ExportTaskIdentifier.$": "States.Format('{}-{}-{}-{}', $.DBInstanceIdentifier, $.datetimeInfo.Date, $.datetimeInfo.Hour, $.datetimeInfo.Minute)",
        "SourceArn.$": "$.snapshotResult.DbSnapshot.DbSnapshotArn",
        "S3BucketName.$": "$.S3BucketName",
        "S3Prefix.$": "$.DBInstanceIdentifier",
        "IamRoleArn.$": "$.IamRoleArn",
        "KmsKeyId.$": "$.KmsKeyId"
      },
      "Next": "Wait10Seconds"
    },
    "Wait10Seconds": {
      "Type": "Wait",
      "Seconds": 10,
      "Next": "DescribeExportTask"
    },
    "DescribeExportTask": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:describeExportTasks",
      "Parameters": {
        "ExportTaskIdentifier.$": "$.ExportTaskIdentifier"
      },
      "ResultPath": "$.describeExportTask",
      "Next": "CheckExportTaskStatus"
    },
    "CheckExportTaskStatus": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.describeExportTask.ExportTasks[0].Status",
          "StringEquals": "COMPLETE",
          "Next": "SuccessState"
        },
        {
          "Or": [
            {
              "Variable": "$.describeExportTask.ExportTasks[0].Status",
              "StringEquals": "STARTING"
            },
            {
              "Variable": "$.describeExportTask.ExportTasks[0].Status",
              "StringEquals": "IN_PROGRESS"
            }
          ],
          "Next": "Wait60Seconds"
        }
      ],
      "Default": "FailState"
    },
    "Wait60Seconds": {
      "Type": "Wait",
      "Seconds": 60,
      "Next": "DescribeExportTask"
    },
    "SuccessState": {
      "Type": "Succeed"
    },
    "FailState": {
      "Type": "Fail",
      "Cause": "Export task failed or was canceled"
    }
  },
  "TimeoutSeconds": 3600
}
