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
          "ErrorEquals": ["States.ALL"],
          "Next": "Fail State"
        }
      ],
      "Next": "Prepare Input for Export Validation",
      "ResultPath": "$.ScannerLambdaResult"
    },
    "Prepare Input for Export Validation": {
      "Type": "Pass",
      "Parameters": {
        "original_input.$": "$",
        "scanner_result.$": "$.ScannerLambdaResult"
      },
      "ResultPath": "$.ValidationInput",
      "Next": "Export Validation Orchestrator"
    },
    "Export Validation Orchestrator": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${ExportValidationOrchestratorLambdaArn}",
        "Payload.$": "$.ValidationInput.original_input"
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
          "ErrorEquals": ["States.ALL"],
          "Next": "Fail State"
        }
      ],
      "Next": "Export Data",
      "ResultPath": "$.ExportValidationResult"
    },
    "Export Data": {
      "Type": "Map",
      "ItemsPath": "$.ValidationInput.scanner_result.Payload.chunks",
      "ItemSelector": {
        "chunk": {
          "table.$": "$$.Map.Item.Value.table",
          "query.$": "$$.Map.Item.Value.query",
          "database.$": "$$.Map.Item.Value.database",
          "extraction_timestamp.$": "$.ValidationInput.original_input.extraction_timestamp"
        },
        "db_endpoint.$": "$.ValidationInput.original_input.db_endpoint",
        "db_username.$": "$.ValidationInput.original_input.db_username",
        "db_name.$": "$.ValidationInput.original_input.db_name",
        "output_bucket.$": "$.ValidationInput.original_input.output_bucket",
        "name.$": "$.ValidationInput.original_input.name"
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
                "db_username.$": "$.db_username",
                "output_bucket.$": "$.output_bucket"
              }
            },
            "Retry": [
              {
                "ErrorEquals": ["States.ALL"],
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
      "Next": "RowCount Updater"
    },
    "RowCount Updater": {
      "Type": "Map",
      "ItemsPath": "$.ValidationInput.scanner_result.Payload.chunks",
      "ItemSelector": {
        "chunk": {
          "table.$": "$$.Map.Item.Value.table",
          "extraction_timestamp.$": "$.ValidationInput.original_input.extraction_timestamp"
        },
        "db_name.$": "$.ValidationInput.original_input.db_name",
        "output_bucket.$": "$.ValidationInput.original_input.output_bucket"
      },
      "MaxConcurrency": ${max_concurrency},
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "INLINE"
        },
        "StartAt": "Invoke Export Processor - RowCount",
        "States": {
          "Invoke Export Processor - RowCount": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "OutputPath": "$.Payload",
            "Parameters": {
              "FunctionName": "${ExportValidationRowCountUpdaterLambdaArn}",
              "chunk.$": "$.chunk"
            },
            "Retry": [
              {
                "ErrorEquals": ["States.ALL"],
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
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "Fail State"
        }
      ],
      "Next": "Prepare Input for Delete"
    },
    "Prepare Input for Delete": {
      "Type": "Pass",
      "Parameters": {
        "db_endpoint.$": "$.ValidationInput.original_input.db_endpoint",
        "db_name.$": "$.ValidationInput.original_input.db_name",
        "output_bucket.$": "$.ValidationInput.original_input.output_bucket",
        "db_username.$": "$.ValidationInput.original_input.db_username",
        "name.$": "$.ValidationInput.original_input.name",
        "extraction_timestamp.$": "$.ValidationInput.original_input.extraction_timestamp"
      },
      "Next": "call database-delete Step Functions"
    },
    "call database-delete Step Functions": {
      "Type": "Task",
      "Resource": "arn:aws:states:::states:startExecution.sync",
      "Parameters": {
        "StateMachineArn": "${DatabaseDeleteStateMachineArn}",
        "Input": {
          "db_endpoint.$": "$.db_endpoint",
          "db_name.$": "$.db_name",
          "output_bucket.$": "$.output_bucket",
          "db_username.$": "$.db_username",
          "name.$": "$.name",
          "extraction_timestamp.$": "$.extraction_timestamp",
          "AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID.$": "$$.Execution.Id"
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
