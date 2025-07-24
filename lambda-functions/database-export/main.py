import os
import boto3
import json
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

def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = event["db_endpoint"]
    db_pw_secret_arn = os.environ["DATABASE_PW_SECRET_ARN"]
    db_name = os.environ.get("DATABASE_NAME", "master")
    output_bucket = os.environ["OUTPUT_BUCKET"]
    db_username = event["db_username"]

    chunk = event["chunk"]
    db_name = chunk["database"]
    db_schema = chunk["schema"]
    db_table = chunk["table"]
    db_query = chunk["query"]
    chunk_index = chunk["chunk_index"]
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
        conn = pymssql.connect(server=db_endpoint, user=db_username,
                       password=db_password, database=db_name, tds_version="7.4")

        df = pd.read_sql_query(db_query, conn)
        logger.info("Data fetched successfully!")

        # # TODO: Fix the issue with the column types (And do more thorough testing of decoding)
        # # TODO: Glue table definition needs to be fixed at the same time in the scanner lambda
        # # Convert all columns to string type
        # for col in df.select_dtypes(include=["object"]).columns:
        #     df[col] = df[col].apply(decode_cp1252)
        
        for col in df.columns:
            non_nulls = df[col].dropna()
            if not non_nulls.empty and isinstance(non_nulls.iloc[0], (bytes, bytearray)):
                logger.info(f"Decoding column '{col}' with fallback decoding")
                df[col] = df[col].apply(lambda x: safe_decode(x) if isinstance(x, (bytes, bytearray)) else x)

        # df = df.astype(str)
        df["extraction_timestamp"] = extraction_timestamp

        wr.s3.to_parquet(
            df=df,
            dataset=True,
            mode="append",
            database=db_name,
            table=db_table,
            partition_cols=["extraction_timestamp"]
        )

        logger.info("Data exported to S3 successfully!")
    except Exception as e:
        logger.error("Error connecting to the database: %s", e)
        raise Exception("Chunk export error")
