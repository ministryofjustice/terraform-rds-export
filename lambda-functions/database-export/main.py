import os
import boto3
import json
import time
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
import pandas as pd
import awswrangler as wr

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")

def fetch_and_write_data(engine, offset, limit):
    query = f"""
    SELECT *
    FROM dbo.Person
    ORDER BY dob
    OFFSET {offset} ROWS
    FETCH NEXT {limit} ROWS ONLY;
    """
    with engine.connect() as connection:
        df_chunk = pd.read_sql(query, connection)
    wr.s3.to_parquet(
        df=df_chunk,
        path=f"s3://serj-test-rds-export-1/mssql_part_{offset}_{limit}.parquet",
    )


def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = os.environ["DATABASE_ENDPOINT"]
    db_secret_arn = os.environ["DATABASE_SECRET_ARN"]
    db_name = os.environ.get("DATABASE_NAME", "master")

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
        mssql_engine = create_engine(
            f"mssql+pymssql://{db_username}:{db_password}@{db_endpoint}:1433/restoredData20250319151623",
            # disable default reset-on-return scheme
            pool_reset_on_return=None,
        )

        fetch_and_write_data(mssql_engine, 0, 1000000)


        print("Data exported to S3 successfully!")

    except Exception as e:
        logger.error("Error connecting to the database: %s", e)
