import os
import boto3
import json
import pytds
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")


def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = os.environ["DATABASE_ENDPOINT"]
    db_secret_arn = os.environ["DATABASE_SECRET_ARN"]
    db_name = os.environ.get("DATABASE_NAME", "master")
    bak_upload_bucket = event.get("bak_upload_bucket")
    bak_upload_key = event.get("bak_upload_key")

    if not bak_upload_bucket or not bak_upload_key:
        logger.error("Missing 'bak_upload_bucket' or 'bak_upload_key' in the event")
        return

    s3_arn_to_restore_from = f"arn:aws:s3:::{bak_upload_bucket}/{bak_upload_key}"

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
        # Connect to the MS SQL Server database using python-tds
        conn = pytds.connect(
            server=db_endpoint,
            database=db_name,
            user=db_username,
            password=db_password,
            timeout=5
        )
        cursor = conn.cursor()
        logger.info("Connected to MS SQL Server successfully!")

        now = datetime.now()
        now = now.strftime("%Y%m%d%H%M%S")
        db_name = f"restoredData{now}"

        # Run the restore command with the S3 ARN from the environment variable.
        restore_command = (
            "exec msdb.dbo.rds_restore_database "
            f"@restore_db_name='{db_name}', "
            f"@s3_arn_to_restore_from='{s3_arn_to_restore_from}';"
        )
        logger.info("Executing restore command: %s", restore_command)
        cursor.execute(restore_command)

        # Loop through result sets until we find one with data.
        result = None
        task_id = None
        while True:
            try:
                result = cursor.fetchone()
                if result:
                    task_id = result[0]  # task_id is the first column in the result row.
                    logger.info("Task ID returned: %s", task_id)
                    break
            except Exception as fetch_error:
                # If the current result set has no rows, move to the next one.
                logger.debug("No results in current result set: %s", fetch_error)

            # Move to the next result set; if there are none, exit the loop.
            if not cursor.nextset():
                logger.error("No further result sets available; task_id not found.")
                raise Exception("No result returned from restore command.")

        conn.commit()
        logger.info("Restore command executed successfully!")

        # Information to return to the state machine
        return {
            "task_id": task_id,
            "current_time": datetime.now().replace(microsecond=0).isoformat(),
            "db_name": db_name,
            "db_identifier": db_endpoint.split(".")[0]
            }
    except Exception as e:
        logger.exception("Error connecting to MS SQL Server or executing command")
        return {
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "db_identifier": db_endpoint.split(".")[0]
        }
    finally:
        try:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
        except Exception as cleanup_error:
            logger.warning("Error during cleanup: %s", cleanup_error)
