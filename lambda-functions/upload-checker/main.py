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
    # List all files in the upload bucket
    list_bucket_objects = s3.list_objects(Bucket=backup_uploads_bucket)
    objects = {obj["Key"]: obj["LastModified"] for obj in list_bucket_objects['Contents']}

    # Check if the artefact_prefix.txt file exists
    if "artefact_prefix.txt" not in objects:
        logger.warn("artefact_prefix.txt does not exist")
        return

    # Open the artefact_prefix.txt file
    artefact_prefix = s3.get_object(Bucket=backup_uploads_bucket, Key="artefact_prefix.txt")
    artefact_prefix = artefact_prefix["Body"].read().decode("utf-8")
    prefix, file_number = artefact_prefix.split(" ")
    logger.info(f"artefact_prefix: {prefix} with {file_number} files")

    # Check if objects has the correct number of files for the prefix
    prefix_objects = [ key for key in objects.keys() if key.startswith(prefix) ]
    if len(prefix_objects) != int(file_number):
        logger.warn(f"Number of files in {prefix} does not match the number of files in artefact_prefix.txt")
        return

    logger.info(f"Number of files in {prefix} matches the number of files in artefact_prefix.txt")

    try:
        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({"bucket": backup_uploads_bucket, "artefacts": f"{prefix}*"})
        )
        logger.info(f"Step function triggered: {response['executionArn']}")
    except Exception as e:
        logger.error(f"Failed to trigger step function: {str(e)}")
