import os
import boto3
import logging
import pymssql
import pandas as pd
import awswrangler as wr

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")


def safe_decode(val):
    """Attempt to decode bytes using CP1252, then UTF-8, then Latin-1 as fallback."""
    if not isinstance(val, (bytes, bytearray)):
        return val

    for encoding in ("cp1252", "utf-8", "latin1"):
        try:
            return val.decode(encoding)
        except UnicodeDecodeError:
            continue

    logger.warning("Failed to decode bytes: %s", val.hex())
    return val.decode("cp1252", errors="replace")

def get_rowversion_cols(conn, table, schema="dbo"):
    """Return a set of colum names that are rowversion/timestamp for a given table."""
    sql = """
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        AND DATA_TYPE IN ('timestamp', 'rowversion')
    """

    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        return {row[0] for row in cur.fetchall()}

def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = event["db_endpoint"]
    db_pw_secret_arn = os.environ["DATABASE_PW_SECRET_ARN"]
    database_refresh_mode = os.environ["DATABASE_REFRESH_MODE"]
    db_name = os.environ.get("DATABASE_NAME", "master")
    db_username = event["db_username"]

    chunk = event["chunk"]
    db_name = chunk["database"]
    db_table = chunk["table"]
    db_query = chunk["query"]
    extraction_timestamp = chunk["extraction_timestamp"]

    # Fetch credentials from AWS Secrets Manager
    try:
        secret_response = secretmanager.get_secret_value(SecretId=db_pw_secret_arn)
        db_password = secret_response["SecretString"]
    except Exception as e:
        logger.error("Error fetching secret: %s", e)
        return

    try:
        # Connect to the MS SQL Server database
        logger.info("Creating the SQLAlchemy engine")
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version="7.4",
        )

        df = pd.read_sql_query(db_query, conn)
        logger.info(f"Data fetched successfully for {db_name}.{db_table} !")
        
        row_version_cols = get_rowversion_cols(conn, table=db_table, schema="dbo")
        logger.info(f"Columns with datatype 'timestamp' or 'rowversion' for {db_table}: {row_version_cols}")

        # # Done: Fix the issue with the column types (And do more thorough testing of decoding)
        # # Done: Glue table definition needs to be fixed at the same time in the scanner lambda

        for col in df.columns:
            non_nulls = df[col].dropna()
            if col in row_version_cols:
                df[col] = df[col].map(lambda v: v.hex())
            elif not non_nulls.empty and isinstance(
                non_nulls.iloc[0], (bytes, bytearray)
            ):
                logger.info(f"Decoding column '{col}' with fallback decoding")
                df[col] = df[col].apply(
                    lambda x: safe_decode(x) if isinstance(x, (bytes, bytearray)) else x
                )

        df = df.astype(str)

        if database_refresh_mode == "incremental":
            df["extraction_timestamp"] = extraction_timestamp

        wr.s3.to_parquet(
            df=df,
            dataset=True,
            mode="append",
            database=db_name,
            table=db_table,
            partition_cols=(
                ["extraction_timestamp"]
                if database_refresh_mode == "incremental"
                else None
            ),
        )

        logger.info(f"Data exported to S3 successfully for {db_name}.{db_table} !")
    except Exception as e:
        raise e
