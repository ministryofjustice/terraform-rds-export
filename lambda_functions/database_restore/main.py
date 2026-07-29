"""Lambda function to restore an RDS database from a .bak backup file."""

from datetime import datetime
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


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Lambda handler to restore an RDS database from a .bak backup file.

    Drops the existing database if present, executes the RDS restore command
    using the S3 backup location, and returns the task ID for status monitoring.

    Args:
        event: Lambda event containing:
            - DescribeDBResult: Dict with DbInstanceDetails including Endpoint
              and MasterUsername
            - bak_upload_bucket: S3 bucket containing backup file
            - bak_upload_key: S3 key path to backup file
            - db_name: Database name to restore
        context: Lambda context object.

    Returns:
        Dict with task_id for status monitoring and db_name.

    Raises:
        ValueError: If required event keys or environment variables are missing.
        Exception: If database restore command fails.
    """
    # Validate required event keys
    try:
        validate_event_keys(
            event,
            [
                "DescribeDBResult",
                "bak_upload_bucket",
                "bak_upload_key",
                "db_name",
            ],
        )
    except ValueError as e:
        logger.error(f"Invalid event structure: {e}")
        raise

    # Validate required environment variables
    try:
        env_vars = validate_env_vars([ENV_DATABASE_PW_SECRET_ARN])
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    # Extract database connection details
    db_details = event["DescribeDBResult"]["DbInstanceDetails"]
    db_endpoint = db_details["Endpoint"]["Address"]
    db_username = db_details["MasterUsername"]
    bak_upload_bucket = event["bak_upload_bucket"]
    bak_upload_key = event["bak_upload_key"]
    db_name = event["db_name"]

    s3_arn_to_restore_from = f"arn:aws:s3:::{bak_upload_bucket}/{bak_upload_key}"

    # Fetch database password from Secrets Manager
    try:
        db_password = get_secret_value(env_vars[ENV_DATABASE_PW_SECRET_ARN])
    except Exception as e:
        logger.error(f"Failed to retrieve database credentials: {e}")
        raise Exception("Error fetching database credentials from Secrets Manager.")

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
            autocommit=True,
        )
        cursor = conn.cursor()
        logger.info("Connected to MS SQL Server successfully")

        # Drop existing database if present
        drop_command = (
            f"IF DB_ID(N'{db_name}') IS NOT NULL "
            "BEGIN "
            f"ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{db_name}]; "
            "END"
        )
        logger.info(f"Executing drop-if-exists command for database: {db_name}")
        cursor.execute(drop_command)
        conn.commit()

        # Execute restore command
        restore_command = (
            "exec msdb.dbo.rds_restore_database "
            f"@restore_db_name='{db_name}', "
            f"@s3_arn_to_restore_from='{s3_arn_to_restore_from}';"
        )
        logger.info(f"Executing restore command for database: {db_name}")
        cursor.execute(restore_command)

        # Extract task ID from result sets
        task_id = None
        while True:
            try:
                result = cursor.fetchone()
                if result:
                    task_id = result[0]  # task_id is first column
                    logger.info(f"Task ID returned: {task_id}")
                    break
            except Exception as fetch_error:
                logger.debug(f"No results in current result set: {fetch_error}")

            if not cursor.nextset():
                logger.error("No further result sets; task_id not found")
                raise Exception("No result returned from restore command.")

        conn.commit()
        logger.info(f"Restore command executed successfully for database: {db_name}")

        logger.info("Database restore initiated successfully")
        return {
            "task_id": task_id,
            "current_time": datetime.now().replace(microsecond=0).isoformat(),
            "db_name": db_name,
            "db_identifier": db_endpoint.split(".")[0],
        }

    except Exception as e:
        logger.exception("Error connecting to MS SQL Server or executing command")
        from datetime import timezone

        return {
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "db_identifier": db_endpoint.split(".")[0],
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
