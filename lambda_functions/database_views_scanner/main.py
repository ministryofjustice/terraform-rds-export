"""Lambda function to extract database view definitions and export to Parquet."""

from typing import Any

import awswrangler as wr
import pandas as pd
import pymssql

from shared.constants import (
    ASPNET_VIEW_PREFIX,
    ENV_DATABASE_PW_SECRET_ARN,
    TDS_VERSION,
)
from shared.utils import (
    configure_logging,
    get_secret_value,
    validate_env_vars,
    validate_event_keys,
)

logger = configure_logging()

# SQL query to extract view definitions
GET_VIEWS_QUERY = """
    SELECT
        v.name AS view_name,
        sm.definition AS view_definition
    FROM sys.views v
    JOIN sys.sql_modules sm ON v.object_id = sm.object_id
    WHERE v.name NOT LIKE %s
    ORDER BY v.name;
"""

# Table name for storing view definitions
VIEW_DEFINITIONS_TABLE = "view_definitions"


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Lambda handler to extract and export database view definitions.

    Retrieves all view definitions from the source database and exports
    them to S3 in Parquet format for documentation and analysis purposes.

    Args:
        event: Lambda event containing:
            - db_endpoint: RDS endpoint address
            - db_username: Database username
            - db_name: Database name
            - extraction_timestamp: Timestamp for extraction
            - output_bucket: S3 bucket for output
        context: Lambda context object.

    Returns:
        Dict with export status message.

    Raises:
        ValueError: If required event keys or environment variables are missing.
        Exception: If database query or S3 write fails.
    """
    # Validate required event keys
    try:
        validate_event_keys(
            event,
            [
                "db_endpoint",
                "db_username",
                "db_name",
                "extraction_timestamp",
                "output_bucket",
            ],
        )
    except ValueError as e:
        logger.error(f"Invalid event structure: {e}")
        raise

    # Validate required environment variables
    try:
        env_vars = validate_env_vars([ENV_DATABASE_PW_SECRET_ARN])
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    # Extract parameters
    db_endpoint = event["db_endpoint"]
    db_username = event["db_username"]
    db_name = event["db_name"]
    extraction_timestamp = event["extraction_timestamp"]
    output_bucket = event["output_bucket"]

    db_password = get_secret_value(env_vars[ENV_DATABASE_PW_SECRET_ARN])

    # Connect to database and fetch view definitions
    try:
        logger.info(f"Connecting to {db_endpoint}, database: {db_name}")
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version=TDS_VERSION,
        )

        df = pd.read_sql_query(GET_VIEWS_QUERY, conn, params=[ASPNET_VIEW_PREFIX])
        view_count = len(df)
        logger.info(f"Fetched {view_count} view definitions from {db_name}")
        conn.close()

    except Exception as e:
        logger.exception(f"Failed to fetch view definitions from database: {e}")
        raise

    # Prepare data for export
    try:
        df = df.astype(str)
        df["extraction_timestamp"] = extraction_timestamp
    except Exception as e:
        logger.exception(f"Failed during data transformation: {e}")
        raise

    # Write view definitions to S3
    try:
        output_path = f"s3://{output_bucket}/{db_name}/{VIEW_DEFINITIONS_TABLE}/"
        logger.info(f"Writing view definitions to S3: {output_path}")

        wr.s3.to_parquet(
            df=df,
            path=output_path,
            database=db_name,
            table=VIEW_DEFINITIONS_TABLE,
            dataset=True,
            mode="overwrite",
        )

        logger.info(
            f"Successfully exported {view_count} view definitions to {output_path}"
        )

        return {
            "export_view_status": f"{view_count} definitions extracted to {output_path}"
        }

    except Exception as e:
        logger.exception(f"Failed to write view definitions to S3 for {db_name}: {e}")
        raise

        raise
