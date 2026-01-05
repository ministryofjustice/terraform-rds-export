import json
import logging
import os
import boto3
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

stepfunctions = boto3.client("stepfunctions")


# Checks the file ends with a .bak prefix before triggering the database restore process
def handler(event, context):
    try:
        state_machine_arn = os.environ["STATE_MACHINE_ARN"]

        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # S3 key should end in .bak
        file_type = key[-4:]
        if file_type.lower() != ".bak":
            error_msg = "Invalid file format. Expected a .bak file."
            logger.error(error_msg)
            raise ValueError(error_msg)

        db_name = os.environ["DB_NAME"]

        logger.info(f"File uploaded: s3://{bucket}/{key}")

        extraction_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%SZ")

        state_machine_input_payload = {
            "bak_upload_bucket": bucket,
            "bak_upload_key": key,
            "db_name": db_name,
            "extraction_timestamp": extraction_timestamp,
            "output_bucket": os.environ["OUTPUT_BUCKET"],
            "name": os.environ["NAME"],
            "environment": os.environ["ENVIRONMENT"],
        }

        # Start Step Function with file info
        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(state_machine_input_payload),
        )

        logger.info(f"Step Function started: {response['executionArn']}")
    except Exception as e:
        logger.error(f"Error triggering Step Function: {str(e)}")
        raise
