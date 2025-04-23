import os
import boto3
import json
import pytds
import time
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
    login_db_name = os.environ.get("DATABASE_NAME", "master")
    restore_db_name = event["db_name"]
    task_id = event["task_id"]

    # Fetch credentials from AWS Secrets Manager
    try:
        secret_response = secretmanager.get_secret_value(SecretId=db_secret_arn)
        db_secret = json.loads(secret_response["SecretString"])
        db_username = db_secret["username"]
        db_password = db_secret["password"]
    except Exception as e:
        logger.error("Error fetching secret: %s", e)
        return

    time.sleep(0.5)

    try:
        # Connect to the MS SQL Server database using python-tds
        conn = pytds.connect(
            server=db_endpoint,
            database=login_db_name,
            user=db_username,
            password=db_password,
            timeout=5
        )
        cursor = conn.cursor()
        logger.info("Connected to MS SQL Server successfully!")

        # Run the restore status command.
        restore_status_command = (
            "exec msdb.dbo.rds_task_status "
            f"@db_name='{restore_db_name}', "
            f"@task_id='{task_id}';"
        )
        logger.info("Executing task status command: %s", restore_status_command)
        cursor.execute(restore_status_command)

        restore_status = "UNKNOWN"
        # Iterate through the result sets to retrieve the task status.
        while True:
            try:
                row = cursor.fetchone()
                if row and len(row) >= 6:
                    logger.info("Received row: %s", row)
                    # Retrieve the lifecycle status from column index 5.
                    restore_status = row[5]
                    logger.info("Task lifecycle from database: %s", restore_status)
                    break
            except Exception as fetch_error:
                logger.debug("Error fetching row: %s", fetch_error)
            if not cursor.nextset():
                logger.error("No further result sets available; status could not be determined.")
                break

    except Exception as e:
        logger.error("Error executing restore_status_command: %s", e)
        raise

    finally:
        cursor.close()
        conn.close()

    return {
        "restore_status": restore_status
    }
