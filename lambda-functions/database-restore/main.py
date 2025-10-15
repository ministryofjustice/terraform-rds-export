import os
import boto3
import pytds
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")


def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = event["DescribeDBResult"]["DbEndpoint"]
    db_pw_secret_arn = os.environ["DATABASE_PW_SECRET_ARN"]
    bak_upload_bucket = event.get("bak_upload_bucket")
    bak_upload_key = event.get("bak_upload_key")
    db_name = event.get("db_name")
    db_username = event["DescribeDBResult"]["DbUsername"]

    if not bak_upload_bucket or not bak_upload_key or not db_name:
        logger.error(
            "Missing 'bak_upload_bucket' or 'bak_upload_key' or 'db_name' in event."
        )
        raise ValueError("Required parameters are missing in the event.")

    s3_arn_to_restore_from = f"arn:aws:s3:::{bak_upload_bucket}/{bak_upload_key}"

    # Fetch credentials from AWS Secrets Manager
    try:
        secret_response = secretmanager.get_secret_value(SecretId=db_pw_secret_arn)
        db_password = secret_response["SecretString"]
    except Exception as e:
        logger.error("Error fetching secret: %s", e)
        raise Exception("Error fetching database credentials from Secrets Manager.")

    try:
        # Connect to the MS SQL Server database using python-tds
        conn = pytds.connect(
            server=db_endpoint,
            database="master",
            user=db_username,
            password=db_password,
            timeout=5,
            autocommit=True,
        )
        cursor = conn.cursor()
        logger.info("Connected to MS SQL Server successfully!")

        drop_command = (
            f"IF DB_ID(N'{db_name}') IS NOT NULL "
            "BEGIN "
            f"ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{db_name}]; "
            "END"
        )
        logger.info("Executing drop-if-exists command: %s", drop_command)
        cursor.execute(drop_command)
        conn.commit()

        now = datetime.now()
        now = now.strftime("%Y%m%d%H%M%S")

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
                    task_id = result[
                        0
                    ]  # task_id is the first column in the result row.
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
            "db_identifier": db_endpoint.split(".")[0],
        }
    except Exception as e:
        logger.exception("Error connecting to MS SQL Server or executing command")
        return {
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.now(datetime.timezone.utc).isoformat() + "Z",
            "db_identifier": db_endpoint.split(".")[0],
        }
    finally:
        try:
            if "cursor" in locals():
                cursor.close()
            if "conn" in locals():
                conn.close()
        except Exception as cleanup_error:
            logger.warning("Error during cleanup: %s", cleanup_error)
