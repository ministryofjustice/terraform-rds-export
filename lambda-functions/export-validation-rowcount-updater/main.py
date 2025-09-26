import os
import logging
import boto3
import pandas as pd
import awswrangler as wr
import time
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

athena = boto3.client("athena")

def run_athena_query(query, database, workgroup):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    query_id = response["QueryExecutionId"]

    # Wait for completion
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break
        time.sleep(2)

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
        raise Exception(f"Athena query failed: {state} - {reason}")

    return query_id

def get_query_result(query_id):
    result = athena.get_query_results(QueryExecutionId=query_id)
    try:
        return result["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"]
    except (IndexError, KeyError):
        return "0"

def lambda_handler(event, context):
    schema = event["db_name"]
    table = event["table_name"]
    extraction_timestamp = event["extraction_timestamp"]
    
    stats_table = "table_export_validation"
    output_bucket = event["output_bucket"]
    workgroup = os.environ.get("ATHENA_WORKGROUP", "primary")
    refresh_mode = os.environ.get("DATABASE_REFRESH_MODE", "full")

    try:
        # Build Athena query
        if refresh_mode == "incremental":
            count_query = f"""
                SELECT COUNT(*) AS row_count, {table} as table_name
                FROM "{schema}"."{table}"
                WHERE extraction_timestamp = '{extraction_timestamp}'
            """
        else:
            count_query = f"""
                SELECT COUNT(*) AS row_count, {table} as table_name
                FROM "{schema}"."{table}"
            """

        query_id = run_athena_query(count_query, schema, workgroup)
        count = get_query_result(query_id)
        logger.info(f"Got {count} rows for {schema}.{table} ({refresh_mode})")

        merge_query = f"""
        MERGE INTO {schema}.table_export_validation AS target
        USING (
            {count_query}
        ) AS source
        ON  target.table_name = source.table_name
        WHEN MATCHED THEN UPDATE SET
            exported_row_count = source.row_count
        )
        """

        # Run the query
        run_athena_query(merge_query, schema, workgroup)

        return { "status": "success", "table": f"{schema}.{table}", "count": count }

    except Exception as e:
        logger.error(f"Failed to update stats for {schema}.{table}: {str(e)}")
        raise e
