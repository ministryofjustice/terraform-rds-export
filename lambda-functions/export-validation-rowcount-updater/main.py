import os
import logging
import boto3
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

athena = boto3.client("athena")

# Queries the exported data in Athena
# Returns the row count of each table exported
# Writes the row count to the row_count_table in Athena


def run_athena_query(query, database, bucket):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": f"s3://{bucket}/athena-results/"},
    )
    query_id = response["QueryExecutionId"]

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


def handler(event, context):
    chunk = event["chunk"]
    db_name = chunk["database"]
    db_table = chunk["table"]
    extraction_timestamp = chunk["extraction_timestamp"]

    stats_table = "table_export_validation"
    output_bucket = os.environ["OUTPUT_BUCKET"]
    refresh_mode = os.environ.get("DATABASE_REFRESH_MODE", "full")

    try:
        if refresh_mode == "incremental":
            count_query = f"""
                SELECT COUNT(*) AS row_count, '{db_table}' AS table_name
                FROM "{db_name}"."{db_table}"
                WHERE extraction_timestamp = '{extraction_timestamp}'
            """
        else:
            count_query = f"""
                SELECT COUNT(*) AS row_count, '{db_table}' AS table_name
                FROM "{db_name}"."{db_table}"
            """

        logger.info("Running row count query:\n%s", count_query)
        query_id = run_athena_query(count_query, db_name, output_bucket)
        exported_row_count = get_query_result(query_id)
        logger.info(
            f"Got {exported_row_count} rows for {db_name}.{db_table} ({refresh_mode})"
        )

        check_query = f"""
            SELECT original_row_count
            FROM "{db_name}".{stats_table}
            WHERE table_name = '{db_table}'
            ORDER BY extraction_timestamp DESC
            LIMIT 1
        """
        query_id = run_athena_query(check_query, db_name, output_bucket)
        result = athena.get_query_results(QueryExecutionId=query_id)

        try:
            original_row_count = result["ResultSet"]["Rows"][1]["Data"][0][
                "VarCharValue"
            ]
        except (IndexError, KeyError):
            original_row_count = "NULL"

        # 1. Delete existing row if exists
        delete_query = f"""
            DELETE FROM {db_name}.{stats_table}
            WHERE table_name = '{db_table}'
            AND extraction_timestamp = '{extraction_timestamp}'
            """
        run_athena_query(delete_query, db_name, output_bucket)

        # 2. Insert updated row
        insert_query = f"""
        INSERT INTO "{db_name}"."{stats_table}"
        SELECT
            '{db_table}' AS table_name,
            {original_row_count} AS original_row_count,
            {exported_row_count} AS exported_row_count,
            '{extraction_timestamp}' AS extraction_timestamp
        """
        run_athena_query(insert_query, db_name, output_bucket)

        return {
            "status": "success",
            "table": f"{db_name}.{db_table}",
            "original_row_count": original_row_count,
            "exported_row_count": exported_row_count,
        }

    except Exception as e:
        logger.error(f"Failed to update stats for {db_name}.{db_table}: {str(e)}")
        raise
