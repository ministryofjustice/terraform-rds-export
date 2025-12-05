{
  "Comment": "All about the database views",
  "StartAt": "Run Database Views Lambda",
  "TimeoutSeconds": 7200,
  "States": {
    "Run Database Views Lambda": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${DatabaseViewsLambdaArn}",
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
      "Next": "Success State",
      "ResultSelector": {
        "Payload.$": "$.Payload"
      },
      "ResultPath": "$.LambdaResult"
    },
    "Fail State": {
      "Type": "Fail",
      "Cause": "Export failed !!"
    },
    "Success State": {
      "Type": "Succeed"
    }
  }
}
