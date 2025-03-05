import json
import logging
import os
import boto3

logger = logging.getLogger()
log_level = os.getenv("LOG_LEVEL", "INFO")
logger.setLevel(log_level)

stepfunctions = boto3.client("stepfunctions")
s3 = boto3.client("s3")
backup_uploads_bucket = os.environ["BACKUP_UPLOADS_BUCKET"]
state_machine_arn = os.environ["STATE_MACHINE_ARN"]

def handler(event, context):
    # List all files in the uplaod bucket
    list_bucket_objects = s3.list_objects(Bucket=backup_uploads_bucket)
    objects = {obj["Key"]: obj["LastModified"] for obj in list_bucket_objects['Contents']}

    # Check if the artefact_list.txt file exists
    if "artefact_list.txt" not in objects:
        logger.warn("artefact_list.txt does not exist")
        return

    # Open the artefact_list.txt file
    artefact_list = s3.get_object(Bucket=backup_uploads_bucket, Key="artefact_list.txt")
    artefact_list = artefact_list["Body"].read().decode("utf-8")
    artefact_list = artefact_list.split("\n")
    artefact_list = [artefact.strip() for artefact in artefact_list if artefact.strip()]
    logger.info(f"artefact_list: {artefact_list}")

    # Check that the artefact_list matches the files in the bucket
    for artefact in artefact_list:
        if artefact not in objects:
            logger.warn(f"{artefact} does not exist")
            return

    # All files in the artefact_list exist
    logger.info("All files in the artefact_list exist")

    try:
        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({"bucket": backup_uploads_bucket, "artefacts": artefact_list})
        )
        logger.info(f"Step function triggered: {response['executionArn']}")
    except Exception as e:
        logger.error(f"Failed to trigger step function: {str(e)}")
