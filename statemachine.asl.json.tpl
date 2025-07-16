{
  "Comment": "Exports the latest RDS snapshot to S3, creating a new one if necessary",
  "StartAt": "RunDatabaseRestoreLambda",
  "States": {
    "RunDatabaseRestoreLambda": {
      "Type": "Task",
      "Resource": "${DatabaseRestoreLambdaArn}",
      "ResultPath": "$.DatabaseRestoreLambdaResult",
      "Next": "Run Restore Status Check"
    },
    "Run Restore Status Check": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${DatabaseRestoreStatusLambdaArn}",
        "Payload": {
          "task_id.$": "$.DatabaseRestoreLambdaResult.task_id",
          "db_name.$": "$.DatabaseRestoreLambdaResult.db_name"
        }
      },
      "Retry": [
        {
          "ErrorEquals": [ "States.ALL" ],
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
      "Default": "Run Export Scanner Lambda"
    },
    "Wait For Restore Completion": {
      "Type": "Wait",
      "Seconds": 30,
      "Next": "Run Restore Status Check"
    },
    "Run Export Scanner Lambda": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${DatabaseExportScannerLambdaArn}",
        "Payload.$": "$"
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
      "Next": "Export Data",
      "ResultPath": "$.DatabaseExportScannerLambdaResult"
    },
    "Export Data": {
      "Type": "Map",
      "InputPath": "$.DatabaseExportScannerLambdaResult.Payload",
      "ItemsPath": "$.chunks",
      "MaxConcurrency": 5,
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "INLINE"
        },
        "StartAt": "Invoke Export Processor",
        "States": {
          "Invoke Export Processor": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "OutputPath": "$.Payload",
            "Parameters": {
              "FunctionName": "${DatabaseExportProcessorLambdaArn}",
              "Payload": {
                "chunk.$": "$"
              }
            },
            "Retry": [
              {
                "ErrorEquals": [ "States.ALL" ],
                "IntervalSeconds": 5,
                "MaxAttempts": 30,
                "BackoffRate": 1,
                "JitterStrategy": "NONE"
              }
            ],
            "End": true
          }
        }
      },
      "Next": "SuccessState"
    },
    "SuccessState": {
      "Type": "Succeed"
    }
  },
  "TimeoutSeconds": 7200
}
