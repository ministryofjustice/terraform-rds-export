
import json
import logging
import os
import boto3

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

stepfunctions = boto3.client("stepfunctions")
state_machine_arn = os.environ["STATE_MACHINE_ARN"]

def handler(event, context):
    try:
        logger.info("Event received: %s", json.dumps(event))

        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        logger.info(f"File uploaded: s3://{bucket}/{key}")

        # Start Step Function with file info
        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({
                "bak_upload_bucket": bucket,
                "bak_upload_key": key
            })
        )

        logger.info(f"Step Function started: {response['executionArn']}")

    except Exception as e:
        logger.error(f"Error triggering Step Function: {str(e)}")
        raise
