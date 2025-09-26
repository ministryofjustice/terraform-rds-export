{
  "Comment": "Creates a RDS DB Instance to restore a .bak file. Exports the data to S3 and writes to the Glue Catalog. Deletes the DB instance after running or if any errors.",
  "StartAt": "Delete DB Instance If Exists",
  "States": {
    "Delete DB Instance If Exists": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:deleteDBInstance",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-{}-sql-server-backup-export',$.name, $.environment)",
        "SkipFinalSnapshot": true
      },
      "ResultPath": "$.DeleteDBInstance",
      "Next": "Wait For Delete DB",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Create DB Instance",
          "ResultPath": null
        }
      ]
    },
    "Wait For Delete DB": {
      "Type": "Wait",
      "Seconds": 300,
      "Next": "DB Instance Deletion"
    },
    "DB Instance Deletion": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:describeDBInstances",
      "Parameters": {
        "DbInstanceIdentifier.$": "States.Format('{}-{}-sql-server-backup-export',$.name, $.environment)"
      },
      "ResultPath": "$.DescribeDBDeleteResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Create DB Instance",
          "ResultPath": null
        }
      ],
      "Next": "Wait For Delete DB"
    },
    "Create DB Instance": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:rds:createDBInstance",
      "Parameters": {
        "AllocatedStorage": 200,
        "MaxAllocatedStorage": 300,
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
        "DbInstanceIdentifier.$": "States.Format('{}-{}-sql-server-backup-export',$.name, $.environment)"
      },
      "ResultPath": "$.CreateDBResult",
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
        "DbInstanceIdentifier.$": "States.Format('{}-{}-sql-server-backup-export',$.name, $.environment)"
      },
      "ResultPath": "$.DescribeDBResult",
      "Catch": [
        {
          "ErrorEquals": [
            "Rds.DbInstanceNotFoundException"
          ],
          "Next": "Wait For DB Instance",
          "ResultPath": null
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
          "ErrorEquals": [
            "States.ALL"
          ],
          "ResultPath": null,
          "Next": "Fail State"
        }
      ]
    },
    "Run Restore Status Check": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName":  "${DatabaseRestoreStatusLambdaArn}",
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
          "ErrorEquals": [
            "States.ALL"
          ],
          "ResultPath": null,
          "Next": "Fail State"
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
      "Default": "Prepare Input for Export"
    },
    "Prepare Input for Export": {
      "Type": "Pass",
      "Parameters": {
        "db_name.$": "$.db_name",
        "extraction_timestamp.$": "$.extraction_timestamp",
        "output_bucket.$": "$.output_bucket",
        "name.$": "$.name",
        "db_endpoint.$": "$.DescribeDBResult.DbInstances[0].Endpoint.Address",
        "db_username.$": "$.DescribeDBResult.DbInstances[0].MasterUsername",
        "tables_to_export": [],
        "AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID.$": "$$.Execution.Id",
        "environment.$": "$.environment"
      },
      "Next": "call database-export Step Functions"
    },
    "call database-export Step Functions": {
      "Type": "Task",
      "Resource": "arn:aws:states:::states:startExecution.sync",
      "Parameters": {
        "StateMachineArn": "${DatabaseExportStateMachineArn}",
        "Input.$": "$"
      },
      "Next": "Success State",
      "ResultPath": null
    },
    "Wait For Restore Completion": {
      "Type": "Wait",
      "Seconds": 30,
      "Next": "Run Restore Status Check"
    },
    "Fail State": {
      "Type": "Fail",
      "Cause": "Database restore process failed. See previous state for details."
    },
    "Success State": {
      "Type": "Succeed"
    }
  },
  "TimeoutSeconds": 7200
}