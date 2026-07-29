"""Lambda function to check the status of an RDS database restore task."""

import time
from typing import Any

import pytds

from shared.constants import (
    ENV_DATABASE_PW_SECRET_ARN,
    SQL_SERVER_MASTER_DB,
    TDS_TIMEOUT,
)
from shared.utils import (
    configure_logging,
    get_secret_value,
    validate_env_vars,
    validate_event_keys,
)

logger = configure_logging()

# Restore task status values
RESTORE_STATUS_UNKNOWN = "UNKNOWN"
RESTORE_STATUS_ERROR = "ERROR"


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Lambda handler to check the status of an RDS database restore task.

    Queries the RDS task status command to retrieve the lifecycle status
    of an ongoing database restore operation.

    Args:
        event: Lambda event containing:
            - db_endpoint: RDS endpoint address
            - db_username: Database username
            - db_name: Name of database being restored
            - task_id: Task ID returned from restore command
        context: Lambda context object.

    Returns:
        Dict with restore_status (e.g., 'DONE', 'IN_PROGRESS', 'ERROR').

    Raises:
        ValueError: If required event keys or environment variables are missing.
        Exception: If task status cannot be determined.
    """
    # Validate required event keys
    try:
        validate_event_keys(event, ["db_endpoint", "db_username", "db_name", "task_id"])
    except ValueError as e:
        logger.error(f"Invalid event structure: {e}")
        raise

    # Validate required environment variables
    try:
        env_vars = validate_env_vars([ENV_DATABASE_PW_SECRET_ARN])
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    # Extract parameters
    db_endpoint = event["db_endpoint"]
    db_username = event["db_username"]
    restore_db_name = event["db_name"]
    task_id = event["task_id"]
    db_pw_secret_arn = env_vars[ENV_DATABASE_PW_SECRET_ARN]

    # Fetch database password
    try:
        db_password = get_secret_value(db_pw_secret_arn)
    except Exception as e:
        logger.error(f"Failed to retrieve database credentials: {e}")
        raise

    # Allow brief delay for task status to be available
    time.sleep(0.5)

    cursor = None
    conn = None

    try:
        # Connect to MS SQL Server
        conn = pytds.connect(
            server=db_endpoint,
            database=SQL_SERVER_MASTER_DB,
            user=db_username,
            password=db_password,
            timeout=TDS_TIMEOUT,
        )
        cursor = conn.cursor()
        logger.info("Connected to MS SQL Server successfully")

        # Query restore task status
        restore_status_command = (
            "exec msdb.dbo.rds_task_status "
            f"@db_name='{restore_db_name}', "
            f"@task_id='{task_id}';"
        )
        logger.info(f"Executing task status command for task_id: {task_id}")
        cursor.execute(restore_status_command)

        restore_status = RESTORE_STATUS_UNKNOWN

        # Iterate through result sets to extract task status
        while True:
            try:
                row = cursor.fetchone()
                if row and len(row) >= 6:
                    logger.info(f"Received status row: {row}")
                    # Lifecycle status is at column index 5
                    restore_status = row[5]
                    logger.info(f"Task lifecycle status: {restore_status}")

                    if restore_status == RESTORE_STATUS_ERROR and len(row) > 6:
                        logger.error(f"Database restore error: {row[6]}")

                    break
            except Exception as fetch_error:
                logger.debug(f"Error fetching status row: {fetch_error}")

            if not cursor.nextset():
                logger.error("No further result sets; status could not be determined")
                break

    except Exception as e:
        logger.exception(f"Error executing restore status command: {e}")
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return {"restore_status": restore_status}
