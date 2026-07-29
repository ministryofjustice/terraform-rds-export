"""Lambda function to update row count validation statistics in Athena."""

import time
from typing import Any

import boto3

from shared.constants import (
    ATHENA_RESULTS_PREFIX,
    ATHENA_WAIT_INTERVAL,
    ENV_DATABASE_REFRESH_MODE,
    ENV_OUTPUT_BUCKET,
    REFRESH_MODE_INCREMENTAL,
)
from shared.utils import configure_logging, validate_env_vars, validate_event_keys

logger = configure_logging()
athena = boto3.client("athena")

# Statistics table name
STATS_TABLE = "table_export_validation"


def run_athena_query(query: str, database: str, bucket: str) -> str:
    """
    Execute a query in Athena and wait for completion.

    Args:
        query: SQL query string to execute.
        database: Athena database name.
        bucket: S3 bucket for Athena results.

    Returns:
        Query execution ID.

    Raises:
        Exception: If query fails or times out.
    """
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={
            "OutputLocation": f"s3://{bucket}/{ATHENA_RESULTS_PREFIX}"
        },
    )
    query_id = response["QueryExecutionId"]

    # Wait for query completion
    while True:
        status_response = athena.get_query_execution(QueryExecutionId=query_id)
        state = status_response["QueryExecution"]["Status"]["State"]

        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break

        time.sleep(ATHENA_WAIT_INTERVAL)

    if state != "SUCCEEDED":
        reason = status_response["QueryExecution"]["Status"].get(
            "StateChangeReason", "unknown"
        )
        error_msg = f"Athena query failed with state {state}: {reason}"
        logger.error(error_msg)
        raise Exception(error_msg)

    logger.debug(f"Athena query {query_id} completed successfully")
    return query_id


def get_query_result(query_id: str) -> str:
    """
    Retrieve the first result value from an Athena query.

    Args:
        query_id: Athena query execution ID.

    Returns:
        First column value of first data row, or "0" if unavailable.
    """
    result = athena.get_query_results(QueryExecutionId=query_id)
    try:
        return result["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"]
    except (IndexError, KeyError):
        logger.warning(f"No results found for query {query_id}, returning 0")
        return "0"


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Lambda handler to validate and update row count statistics.

    Compares exported row counts with original row counts from the source
    database and stores the validation results in the Athena stats table.
    This enables data quality monitoring throughout the export pipeline.

    Args:
        event: Lambda event containing:
            - chunk: Dict with database, table, extraction_timestamp
        context: Lambda context object.

    Returns:
        Dict with validation results including original and exported row counts.

    Raises:
        ValueError: If required event keys or environment variables are missing.
        Exception: If Athena queries fail.
    """
    # Validate required event structure
    try:
        validate_event_keys(event, ["chunk"])
    except ValueError as e:
        logger.error(f"Invalid event structure: {e}")
        raise

    # Validate required environment variables
    try:
        env_vars = validate_env_vars([ENV_OUTPUT_BUCKET, ENV_DATABASE_REFRESH_MODE])
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    chunk = event["chunk"]
    db_name = chunk["database"]
    db_table = chunk["table"]
    extraction_timestamp = chunk["extraction_timestamp"]

    output_bucket = env_vars[ENV_OUTPUT_BUCKET]
    refresh_mode = env_vars[ENV_DATABASE_REFRESH_MODE]

    try:
        # Query exported row count
        if refresh_mode == REFRESH_MODE_INCREMENTAL:
            count_query = f"""
                SELECT COUNT(*) AS row_count
                FROM "{db_name}"."{db_table}"
                WHERE extraction_timestamp = '{extraction_timestamp}'
            """
        else:
            count_query = f"""
                SELECT COUNT(*) AS row_count
                FROM "{db_name}"."{db_table}"
            """

        logger.info(f"Running row count query for {db_name}.{db_table}")
        query_id = run_athena_query(count_query, db_name, output_bucket)
        exported_row_count = get_query_result(query_id)
        logger.info(
            f"Export validation: {db_name}.{db_table} has {exported_row_count} rows ({refresh_mode} mode)"
        )

        # Query original row count from stats table
        check_query = f"""
            SELECT original_row_count
            FROM "{db_name}"."{STATS_TABLE}"
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
            logger.warning(
                f"Could not retrieve original row count for {db_name}.{db_table}"
            )

        # Update stats table with validation results
        delete_query = f"""
            DELETE FROM "{db_name}"."{STATS_TABLE}"
            WHERE table_name = '{db_table}'
            AND extraction_timestamp = '{extraction_timestamp}'
        """
        run_athena_query(delete_query, db_name, output_bucket)

        insert_query = f"""
            INSERT INTO "{db_name}"."{STATS_TABLE}"
            SELECT
                '{db_table}' AS table_name,
                {original_row_count} AS original_row_count,
                {exported_row_count} AS exported_row_count,
                '{extraction_timestamp}' AS extraction_timestamp
        """
        run_athena_query(insert_query, db_name, output_bucket)

        logger.info(
            f"Row count validation completed for {db_name}.{db_table}: "
            f"original={original_row_count}, exported={exported_row_count}"
        )

        return {
            "status": "success",
            "table": f"{db_name}.{db_table}",
            "original_row_count": original_row_count,
            "exported_row_count": exported_row_count,
        }

    except Exception as e:
        logger.exception(f"Failed to update stats for {db_name}.{db_table}: {e}")
        raise
