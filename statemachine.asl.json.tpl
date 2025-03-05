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
      "Default": "Run Scout Lambda"
    },
    "Wait For Restore Completion": {
      "Type": "Wait",
      "Seconds": 10,
      "Next": "Run Restore Status Check"
    },
    "Run Scout Lambda": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:eu-west-1:684969100054:function:dmet-sql-server-database-export-scout:$LATEST",
        "Payload": {
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
      "Next": "SuccessState",
      "ResultPath": "$.DatabaseExportScoutLambdaResult"
    },
    "SuccessState": {
      "Type": "Succeed"
    }
  },
  "TimeoutSeconds": 3600
}
