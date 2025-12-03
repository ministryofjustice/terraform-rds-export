{
  "Comment": "All about the database views",
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
      "Next": "Export Views",
      "ResultSelector": {
        "Payload.$": "$.Payload"
      },
      "ResultPath": "$.LambdaResult"
    },
    "Export Views": {
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
              "FunctionName": "${DatabaseViewsProcessorLambdaArn}",
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
      "Next": "Prepare Input for Delete",
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
        "tables_to_export": [],
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
