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
    db_name = event["db_name"]
    extraction_timestamp = event["extraction_timestamp"]
    output_bucket = event["output_bucket"]

    # === Get Password ===
    db_password = get_secret_value(db_pw_secret_arn)

    # === Db_query ===
    db_query_views_description = """
    SELECT
        v.name AS view_name,
        sm.definition AS view_definition
    FROM sys.views v
    JOIN sys.sql_modules sm ON v.object_id = sm.object_id
    WHERE v.name not like 'vw_aspnet%'
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

        df = pd.read_sql_query(db_query_views_description, conn)
        view_count = len(df)
        logger.info(f"Fetched {view_count} view descriptions from {db_name}")

    except Exception as e:
        logger.exception(f"Failed to get view information: {e}")
        raise

    # === Decode and Clean Data ===
    try:
        df = df.astype(str)
        df["extraction_timestamp"] = extraction_timestamp
    except Exception as e:
        logger.exception(f"Failed during decoding or transformation: {e}")
        raise

    try:
        table_name = "view_definitions"
        output_path = f"s3://{output_bucket}/{db_name}/{table_name}/"
        logger.info(f"Writing to S3: {output_path}")

        wr.s3.to_parquet(
            df=df,
            path=output_path,
            database=db_name,
            table=table_name,
            dataset=True,
            mode="overwrite",
        )

        logger.info(
            f"Database view descriptions table written successfully to {output_path}"
        )

        logger.info("View information extracted successfully")
        return {
            "export_view_status": f"{view_count} definitions extracted to {output_path}"
        }

    except Exception as e:
        logger.exception(f"Failed to write {table_name} table for {db_name}: {e}")
        raise
