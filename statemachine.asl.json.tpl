{
  "Comment": "Creates a RDS DB Instance to restore a .bak file. Exports the data to S3 and writes to the Glue Catalog. Deletes the DB instance after running or if any errors.",
  "StartAt": "Create DB Instance",
  "States": {
    "Create DB Instance": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:createDBInstance",
      "Parameters": {
        "AllocatedStorage": 100,
        "MaxAllocatedStorage": 200,
        "EnableStorageAutoScaling": true,
        "StorageType": "gp2",
        "StorageEncrypted": true,
        "Engine": "sqlserver-se",
        "EngineVersion": "15.00.4420.2.v1",
        "LicenseModel": "license-included",
        "MasterUsername": "admin",
        "ManageMasterUserPassword": false,
        "MasterUserPassword": "${MasterUserPassword}",
        "DbParameterGroupName": "${ParameterGroupName}",
        "OptionGroupName": "${OptionGroupName}",
        "VpcSecurityGroupIds": ${jsonencode(VpcSecurityGroupIds)},
        "DbSubnetGroupName": "${DbSubnetGroupName}",
        "DbInstanceClass": "db.m5.2xlarge",
        "DbInstanceIdentifier.$": "States.Format('{}-sql-server-backup-export',$.name)"
      },
      "ResultPath": "$.CreateDBResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceAlreadyExistsException"
          ],
          "ResultPath": null,
          "Next": "Describe DB Instance Creation"
        }
      ],
      "Next": "Wait For DB Instance"
    },
    "Wait For DB Instance": {
      "Type": "Wait",
      "Seconds": 300,
      "Next": "Describe DB Instance Creation"
    },
    "Describe DB Instance Creation": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:describeDBInstances",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-sql-server-backup-export',$.name)"
      },
      "ResultPath": "$.DescribeDBResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Wait For DB Instance"
        }
      ],
      "Next": "Choice Start Restore"
    },
    "Choice Start Restore": {
      "Type": "Choice",
      "Choices": [
        {
          "Not": {
            "Variable": "$.DescribeDBResult.DbInstances[0].DbInstanceStatus",
            "StringEquals": "available"
          },
          "Next": "Wait For DB Instance"
        }
      ],
      "Default": "Run Database Restore Lambda"
    },
    "Run Database Restore Lambda": {
      "Type": "Task",
      "Resource": "${DatabaseRestoreLambdaArn}",
      "ResultPath": "$.DatabaseRestoreLambdaResult",
      "Next": "Run Restore Status Check",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": null,
          "Next": "Delete DB Instance"
        }
      ]
    },
    "Run Restore Status Check": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${DatabaseRestoreStatusLambdaArn}",
        "Payload": {
          "task_id.$": "$.DatabaseRestoreLambdaResult.task_id",
          "db_name.$": "$.DatabaseRestoreLambdaResult.db_name",
          "db_endpoint.$": "$.DescribeDBResult.DbInstances[0].Endpoint.Address",
          "db_username.$": "$.DescribeDBResult.DbInstances[0].MasterUsername"
        }
      },
      "Retry": [
        {
          "ErrorEquals": [
            "States.ALL"
          ],
          "IntervalSeconds": 1,
          "MaxAttempts": 3,
          "BackoffRate": 2,
          "JitterStrategy": "FULL"
        }
      ],
      "Next": "Choice Start Export",
      "ResultPath": "$.DatabaseRestoreStatusLambdaResult",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": null,
          "Next": "Delete DB Instance"
        }
      ]
    },
    "Choice Start Export": {
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
      "ResultPath": "$.DatabaseExportScannerLambdaResult",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": null,
          "Next": "Delete DB Instance"
        }
      ]
    },
    "Export Data": {
      "Type": "Map",
      "ItemsPath": "$.DatabaseExportScannerLambdaResult.Payload.chunks",
      "Parameters": {
        "chunk.$": "$$.Map.Item.Value",
        "db_endpoint.$": "$.DescribeDBResult.DbInstances[0].Endpoint.Address",
        "db_username.$": "$.DescribeDBResult.DbInstances[0].MasterUsername",
        "name.$": "$.name"
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
                "BackoffRate": 1,
                "JitterStrategy": "NONE"
              }
            ],
            "End": true
          }
        }
      },
      "ResultPath": null,
      "Next": "Delete DB Instance",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": null,
          "Next": "Delete DB Instance"
        }
      ]
    },
    "Delete DB Instance": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:deleteDBInstance",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-sql-server-backup-export',$.name)",
        "SkipFinalSnapshot": true
      },
      "ResultPath": "$.DeleteDBInstance",
      "Next": "Wait For Delete DB Instance"
    },
    "Wait For Delete DB Instance": {
      "Type": "Wait",
      "Seconds": 180,
      "Next": "Describe DB Instance Deletion"
    },
    "Describe DB Instance Deletion":{
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:describeDBInstances",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-sql-server-backup-export',$.name)"
      },
      "ResultPath": "$.DecribeDBDeleteResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Success State"
        }
      ],
      "Next": "Choice End State"
    },
    "Choice End State": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.DecribeDBDeleteResult.DbInstances[0].DbInstanceStatus",
          "StringEquals": "deleting",
          "Next": "Wait For Delete DB Instance"
        }
      ],
      "Default": "Fail State"
    },
    "Fail State": {
      "Type": "Fail",
      "Cause": "RDS DB Instance not in status: 'deleting'. Check the status."
    },
    "Success State": {
      "Type": "Succeed"
    }
  },
  "TimeoutSeconds": 36000
}