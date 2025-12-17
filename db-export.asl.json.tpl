{
  "Comment": "For tables: creates metadata in Glue Catalog, exports data to S3, returns row count table, then triggers a state machine to export view definitions or to delete the RDS DB instance.",
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
          "ResultPath": "$.error",
          "Next": "Fail State"
        }
      ],
      "Next": "Export Data",
      "ResultSelector": {
        "Payload.$": "$.Payload"
      },
      "ResultPath": "$.LambdaResult"
    },
    "Export Data": {
      "Type": "Map",
      "ItemsPath": "$.LambdaResult.Payload.chunks",
      "ItemSelector": {
        "chunk": {
          "table.$": "$$.Map.Item.Value.table",
          "query.$": "$$.Map.Item.Value.query",
          "database.$": "$$.Map.Item.Value.database"
        },
        "db_endpoint.$": "$.db_endpoint",
        "db_username.$": "$.db_username",
        "db_name.$": "$.db_name",
        "output_bucket.$": "$.output_bucket",
        "name.$": "$.name",
        "extraction_timestamp.$": "$.extraction_timestamp"
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
                "name.$": "$.name",
                "extraction_timestamp.$": "$.extraction_timestamp"
              }
            },
            "Retry": [
              {
                "ErrorEquals" : [
                  "Sandbox.Timedout"
                ],
                "MaxAttempts": 0
              },
              {
                "ErrorEquals": [
                  "States.ALL"
                ],
                "IntervalSeconds": 5,
                "MaxAttempts": 2,
                "BackoffRate": 1,
                "JitterStrategy": "NONE"
              }
            ],
            "Catch": [
              {
                "ErrorEquals": ["Sandbox.Timedout"],
                "ResultPath": "$.error",
                "Next": "Send EventBridge Event"
              }
            ],
            "Next": "Chunk Succeeded"
          },
          "Send EventBridge Event": {
            "Type": "Task",
            "Resource": "arn:aws:states:::aws-sdk:eventbridge:putEvents",
            "Parameters": {
              "Entries": [
                {
                  "Source": "aws.states",
                  "DetailType": "Step Functions Execution Status Change",
                  "Detail": {
                    "executionArn.$": "$$.Execution.Id",
                    "stateMachineArn.$": "$$.StateMachine.Id",
                    "executionName.$": "States.Format('Failed to extract data for {} table.', $.chunk.table)",
                    "status": "TIMED_OUT",
                    "time.$":  "$$.State.EnteredTime",
                    "table.$": "$.chunk.table"
                  }
                }
              ]
            },
            "ResultPath": null,
            "Next": "Timeout Output"
          },
          "Timeout Output": {
            "Type": "Pass",
            "Parameters": {
                  "database.$": "$.chunk.database",
                  "table.$": "$.chunk.table",
                  "status": "TIMED_OUT"
            },
            "Next": "Chunk Succeeded"
          },
          "Chunk Succeeded": {
            "Type": "Succeed"
          }
        }
      },
      "Next": "Transform Output",
      "ResultPath": "$.LambdaResult"
    },
    "Transform Output": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${TransformOutputLambdaArn}",
        "Payload": {
          "chunks.$": "$.LambdaResult"
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
      "ResultPath": "$.LambdaResult"
    },
    "RowCount Updater": {
      "Type": "Map",
      "ItemsPath": "$.LambdaResult.Payload.tables",
      "ItemSelector": {
        "chunk": {
          "table.$": "$$.Map.Item.Value.table",
          "database.$": "$$.Map.Item.Value.database",
          "extraction_timestamp.$": "$.extraction_timestamp"
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
      "Next": "Prepare Input",
      "ResultPath": "$.LambdaResult"
    },
    "Prepare Input": {
      "Type": "Pass",
      "Parameters": {
        "db_name.$": "$.db_name",
        "extraction_timestamp.$": "$.extraction_timestamp",
        "output_bucket.$": "$.output_bucket",
        "name.$": "$.name",
        "db_endpoint.$": "$.db_endpoint",
        "db_username.$": "$.db_username",
        "tables_to_export": [],
        "AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID.$": "$$.Execution.Id",
        "environment.$": "$.environment",
        "DbInstanceIdentifier.$": "$.DbInstanceIdentifier"
      },
      "Next": "Call Next Step Function"
    },
    "Call Next Step Function": {
      "Type": "Task",
      "Resource": "arn:aws:states:::states:startExecution.sync",
      "Parameters": {
        "StateMachineArn": "${LambdaArn}",
        "Input.$": "$"
      },
      "Next": "Success State",
      "ResultPath": null
    },
    "Fail State": {
      "Type": "Fail",
      "Cause": "Database export process failed. See previous state for details."
    },
    "Success State": {
      "Type": "Succeed"
    }
  }
}
