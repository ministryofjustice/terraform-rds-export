import os
import boto3
import logging
import pymssql
import pandas as pd
import awswrangler as wr

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
secretmanager = boto3.client("secretsmanager")


def get_secret_value(secret_arn: str) -> str:
    """Fetch secret string from Secrets Manager."""
    try:
        response = secretmanager.get_secret_value(SecretId=secret_arn)
        return response["SecretString"]
    except Exception:
        logger.exception("Error fetching secret: %s", secret_arn)
        raise


def handler(event, context):
    # === Environment & Event Variables ===
    db_endpoint = event["db_endpoint"]
    db_username = event["db_username"]
    db_pw_secret_arn = os.environ["DATABASE_PW_SECRET_ARN"]
    output_bucket = event["output_bucket"]
    extraction_timestamp = event["extraction_timestamp"]
    db_name = event["db_name"]
    database_refresh_mode = os.environ["DATABASE_REFRESH_MODE"]

    # === Get Password ===
    db_password = get_secret_value(db_pw_secret_arn)

    # === Db_query ===

    db_query = """
    SELECT
        v.name AS view_name,
        sm.definition AS view_definition
    FROM sys.views v
    JOIN sys.sql_modules sm ON v.object_id = sm.object_id
    ORDER BY v.name;
    """

    # === Connect to SQL Server & Fetch Data ===
    try:
        logger.info(f"Connecting to {db_endpoint}, db: {db_name}")
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version="7.4",
        )
        df = pd.read_sql_query(db_query, conn)
        logger.info(f"Fetched {len(df)} rows from {db_name}")
    except Exception as e:
        logger.exception(f"Failed to fetch data from SQL Server: {e}")
        raise

    # === Decode and Clean Data ===
    try:
        df = df.astype(str)
        df["extraction_timestamp"] = extraction_timestamp
    except Exception as e:
        logger.exception(f"Failed during decoding or transformation: {e}")
        raise

    try:
        output_path = f"s3://{output_bucket}/{db_name}/view_definitions/"
        logger.info(
            f"Writing to S3: {output_path}"
            f"{' partitioned by extraction_timestamp' if database_refresh_mode == 'incremental' else ''}"
        )

        wr.s3.to_parquet(
            df=df,
            path=output_path,
            database=db_name,
            table="view_definitions",
            dataset=True,
            mode="append",
            partition_cols=(
                ["extraction_timestamp"]
                if database_refresh_mode == "incremental"
                else None
            ),
        )

        logger.info(f"Data export for views completed: {db_name}. ({len(df)} rows)")
        return {
            "database": db_name,
            "table": "view_definitions",
            "s3_output_path": output_path,
        }

    except Exception as e:
        logger.exception(f"Failed to write view_definitions to S3 for {db_name}: {e}")
        raise
