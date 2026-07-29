"""Lambda function to validate backup file uploads and trigger restore workflow."""

import json
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.constants import (
    BAK_FILE_EXTENSION,
    ENV_DB_NAME,
    ENV_ENVIRONMENT,
    ENV_NAME,
    ENV_OUTPUT_BUCKET,
    ENV_STATE_MACHINE_ARN,
)
from shared.utils import configure_logging, validate_env_vars

logger = configure_logging()
stepfunctions = boto3.client("stepfunctions")


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Lambda handler to validate backup file uploads and trigger state machine.

    Triggered by S3 ObjectCreated events, validates that the uploaded file
    has a .bak extension and then starts a Step Functions state machine
    to orchestrate the restore workflow.

    Args:
        event: S3 event containing bucket and object key information.
        context: Lambda context object.

    Returns:
        Dict with execution ARN and status.

    Raises:
        ValueError: If configuration is missing or file format is invalid.
        ClientError: If Step Functions execution fails.
    """
    try:
        # Validate required environment variables
        env_vars = validate_env_vars(
            [
                ENV_STATE_MACHINE_ARN,
                ENV_DB_NAME,
                ENV_OUTPUT_BUCKET,
                ENV_NAME,
                ENV_ENVIRONMENT,
            ]
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    try:
        # Extract S3 bucket and object key from event
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # Validate file extension
        file_extension = key[-len(BAK_FILE_EXTENSION) :]
        if file_extension.lower() != BAK_FILE_EXTENSION.lower():
            error_msg = (
                f"Invalid file format: {file_extension}. "
                f"Expected a {BAK_FILE_EXTENSION} file."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Valid backup file uploaded: s3://{bucket}/{key}")

        # Prepare state machine input
        extraction_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%SZ")
        state_machine_input = {
            "bak_upload_bucket": bucket,
            "bak_upload_key": key,
            "db_name": env_vars[ENV_DB_NAME],
            "extraction_timestamp": extraction_timestamp,
            "output_bucket": env_vars[ENV_OUTPUT_BUCKET],
            "name": env_vars[ENV_NAME],
            "environment": env_vars[ENV_ENVIRONMENT],
        }

        # Start state machine execution
        response = stepfunctions.start_execution(
            stateMachineArn=env_vars[ENV_STATE_MACHINE_ARN],
            input=json.dumps(state_machine_input),
        )

        logger.info(f"Step Function execution started: {response['executionArn']}")

        return {
            "status": "success",
            "executionArn": response["executionArn"],
            "uploadedFile": f"s3://{bucket}/{key}",
        }

    except KeyError as e:
        error_msg = f"Invalid S3 event structure: missing key {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e

    except Exception as e:
        logger.exception(f"Error processing backup file upload: {e}")
        raise

    except Exception as e:
        logger.error(f"Error triggering Step Function: {str(e)}")
        raise
