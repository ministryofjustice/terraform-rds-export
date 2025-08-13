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
      "ResultPath": "$.ScannerLambdaResult"
    },
    "Export Data": {
      "Type": "Map",
      "ItemsPath": "$.ScannerLambdaResult.Payload.chunks",
      "Parameters": {
        "chunk": {
          "table.$": "$$.Map.Item.Value.table",
          "query.$": "$$.Map.Item.Value.query",
          "database.$": "$$.Map.Item.Value.database",
          "extraction_timestamp.$": "$.extraction_timestamp"
        },
        "db_endpoint.$": "$.db_endpoint",
        "db_username.$": "$.db_username",
        "db_name.$": "$.db_name",
        "output_bucket.$": "$.output_bucket",
        "name.$": "$.name"
      },
      "MaxConcurrency": 20,
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
                "db_username.$": "$.db_username",
                "output_bucket.$": "$.output_bucket"
              }
            },
            "Retry": [
              {
                "ErrorEquals": [
                  "States.ALL"
                ],
                "IntervalSeconds": 5,
                "MaxAttempts": 3,
                "BackoffRate": 1,
                "JitterStrategy": "NONE"
              }
            ],
            "End": true
          }
        }
      },
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
      "Cause": "Export failed !!"
    },
    "Success State": {
      "Type": "Succeed"
    }
  }
}