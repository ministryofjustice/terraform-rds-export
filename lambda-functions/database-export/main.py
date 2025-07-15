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
    now = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

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
        print("Creating the SQLAlchemy engine")
        conn = pymssql.connect(server=db_endpoint, user=db_username,
                       password=db_password, database=db_name)

        df = pd.read_sql_query(db_query, conn)

        wr.s3.to_parquet(
            df=df,
            path=f"s3://{output_bucket}/{db_schema}/{db_table}/{now}_{chunk_index}.parquet",
        )

        print("Data exported to S3 successfully!")
    except Exception as e:
        logger.error("Error connecting to the database: %s", e)
        raise Exception("Chunk export error")
