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
      "Catch": [
        {
          "ErrorEquals": [
            "States.ALL"
          ],
          "Next": "Fail State"
        }
      ],
      "Next": "Export Data",
      "ResultPath": "$.ScannerLambdaResult"
    },
    "Export Data": {
      "Type": "Map",
      "ItemsPath": "$.ScannerLambdaResult.Payload.chunks",
      "ItemSelector": {
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
      "MaxConcurrency": ${max_concurrency},
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "INLINE"
        },
        "StartAt": "Invoke Export Processor - Chunk Export",
        "States": {
          "Invoke Export Processor - Chunk Export": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "OutputPath": "$.Payload",
            "Parameters": {
              "FunctionName": "${DatabaseExportProcessorLambdaArn}",
              "Payload": {
                "chunk.$": "$.chunk",
                "db_endpoint.$": "$.db_endpoint",
                "db_name.$": "$.db_name",
                "db_username.$": "$.db_username",
                "output_bucket.$": "$.output_bucket",
                "name.$": "$.name"
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
      "Next": "Transform Output",
      "ResultPath": null
    },
    "Transform Output": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${TransformOutputLambdaArn}",
        "Payload": {
          "name.$": "$.name",
          "environment.$": "$.environment",
          "extraction_timestamp.$": "$.extraction_timestamp",
          "chunks.$": "$.ScannerLambdaResult.Payload.chunks"
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
      "Next": "RowCount Updater",
      "ResultSelector": {
        "Payload.$": "$.Payload"
      },
      "ResultPath": "$"
    },
    "RowCount Updater": {
      "Type": "Map",
      "ItemsPath": "$.Payload.tables",
      "ItemSelector": {
        "chunk": {
          "table.$": "$$.Map.Item.Value.table",
          "database.$": "$$.Map.Item.Value.database",
          "extraction_timestamp.$": "$.Payload.extraction_timestamp"
        }
      },
      "MaxConcurrency": ${max_concurrency},
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "INLINE"
        },
        "StartAt": "Invoke RowCount Updater",
        "States": {
          "Invoke RowCount Updater": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${ExportValidationRowCountUpdaterLambdaArn}",  
              "Payload": {
                "chunk.$": "$.chunk"
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
            "End": true,
            "OutputPath": "$.Payload"
          }
        }
      },
      "Next": "Prepare Input for Delete",
      "ResultPath": null
    },
    "Prepare Input for Delete": {
      "Type": "Pass",
      "Parameters": {
        "name.$": "$.Payload.name",
        "environment.$": "$.Payload.environment"
      },
      "Next": "call database-delete Step Functions"
    },
    "call database-delete Step Functions": {
      "Type": "Task",
      "Resource": "arn:aws:states:::states:startExecution.sync",
      "Parameters": {
        "StateMachineArn": "${DatabaseDeleteStateMachineArn}",
        "Input": {
          "name.$": "$.name",
          "environment.$": "$.environment"
        }
      },
      "Next": "Success State",
      "ResultPath": null
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
