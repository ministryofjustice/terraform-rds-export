{
  "Comment": "For views: creates a table containing views and their definitions.",
  "StartAt": "Run Database Views Lambda",
  "TimeoutSeconds": 7200,
  "States": {
    "Run Database Views Lambda": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${DatabaseViewsScannerLambdaArn}",
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
      "Catch": [
        {
          "ErrorEquals": [
            "States.ALL"
          ],
          "ResultPath": "$.error",
          "Next": "Fail State"
        }
      ],
      "Next": "Prepare Input for Delete",
      "ResultSelector": {
        "Payload.$": "$.Payload"
      },
      "ResultPath": "$.LambdaResult"
    },
  "Prepare Input for Delete": {
      "Type": "Pass",
      "Parameters": {
        "DbInstanceIdentifier.$": "$.DbInstanceIdentifier",
        "db_name.$": "$.db_name",
        "extraction_timestamp.$": "$.extraction_timestamp",
        "output_bucket.$": "$.output_bucket",
        "name.$": "$.name",
        "AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID.$": "$$.Execution.Id",
        "environment.$": "$.environment"
      },
      "Next": "call database-delete Step Functions"
    },
    "call database-delete Step Functions": {
      "Type": "Task",
      "Resource": "arn:aws:states:::states:startExecution.sync",
      "Parameters": {
        "StateMachineArn": "${DatabaseDeleteStateMachineArn}",
        "Input.$": "$"
      },
      "Next": "Success State",
      "ResultPath": null
    },
    "Fail State": {
      "Type": "Fail",
      "Cause": "Database export views process failed. See previous state for details."
    },
    "Success State": {
      "Type": "Succeed"
    }
  }
}
