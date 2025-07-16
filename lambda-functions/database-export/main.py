import os
import boto3
import json
import logging
from datetime import datetime
import pymssql
import pandas as pd
import awswrangler as wr

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")


def decode_cp1252(val):
    # Only try to decode raw bytes
    if not isinstance(val, (bytes, bytearray)):
        return val

    try:
        # first, strict decode to see if it really is valid
        return val.decode("cp1252")
    except UnicodeDecodeError as e:
        # log the exact bytes and the error
        logger.warning(
            "Decoding error at bytes %s: %s",
            val.hex(),            # hex string of the raw bytes
            e                     # the exception message
        )
        # if strict decode fails, replace invalid characters
        return val.decode("cp1252", errors="replace")


def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = os.environ["DATABASE_ENDPOINT"]
    db_secret_arn = os.environ["DATABASE_SECRET_ARN"]
    db_name = os.environ.get("DATABASE_NAME", "master")
    output_bucket = os.environ["OUTPUT_BUCKET"]

    chunk = event["chunk"]
    db_name = chunk["database"]
    db_schema = chunk["schema"]
    db_table = chunk["table"]
    db_query = chunk["query"]
    chunk_index = chunk["chunk_index"]
    extraction_timestamp = chunk["extraction_timestamp"]

    # Fetch credentials from AWS Secrets Manager
    try:
        secret_response = secretmanager.get_secret_value(SecretId=db_secret_arn)
        db_secret = json.loads(secret_response["SecretString"])
        db_username = db_secret["username"]
        db_password = db_secret["password"]
    except Exception as e:
        logger.error("Error fetching secret: %s", e)
        return

    try:
        # Connect to the MS SQL Server database
        logger.info("Creating the SQLAlchemy engine")
        conn = pymssql.connect(server=db_endpoint, user=db_username,
                       password=db_password, database=db_name, charset='CP1252', tds_version="7.4")

        df = pd.read_sql_query(db_query, conn)
        logger.info("Data fetched successfully!")

        # TODO: Fix the issue with the column types (And do more thorough testing of decoding)
        # TODO: Glue table definition needs to be fixed at the same time in the scanner lambda
        # Convert all columns to string type
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(decode_cp1252)

        df = df.astype(str)
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
