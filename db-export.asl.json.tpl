{
  "Comment": "Exports data to S3 and deletes the RDS DB instance after.",
  "StartAt": "Run Export Scanner Lambda",
  "TimeoutSeconds": 7200,
  "States": {
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
      "ItemsPath": "$.DatabaseExportScannerLambdaResult.Payload.chunks",
      "Parameters": {
        "chunk.$": "$$.Map.Item.Value",
        "DescribeDBResult.$": "$.DescribeDBResult",
        "name.$": "$.name",
        "db_name.$": "$.db_name",
        "output_bucket.$": "$.output_bucket",
        "extraction_timestamp.$": "$.extraction_timestamp"
      },
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
                "chunk.$": "$.chunk",
                "db_endpoint.$": "$.db_endpoint",
                "db_username.$": "$.db_username"
              }
            },
            "Retry": [
              {
                "ErrorEquals": [
                  "States.ALL"
                ],
                "IntervalSeconds": 5,
                "MaxAttempts": 30,
                "BackoffRate": 1
              }
            ],
            "End": true
          }
        }
      },
      "ResultPath": null,
      "Next": "Success State",
      "Catch": [
        {
          "ErrorEquals": [
            "States.ALL"
          ],
          "ResultPath": null,
          "Next": "Fail State"
        }
      ]
    },
    "Fail State": {
      "Type": "Fail",
      "Cause": "Export failed or RDS instance deletion not successful."
    },
    "Success State": {
      "Type": "Succeed"
    }
  }
}