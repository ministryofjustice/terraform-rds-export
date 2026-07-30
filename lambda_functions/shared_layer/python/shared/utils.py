"""Common utilities for Lambda functions in the RDS export pipeline."""

import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()


def configure_logging(log_level: str | None = None) -> logging.Logger:
    """
    Configure logging for Lambda functions.

    Args:
        log_level: Optional log level override. Defaults to environment variable
                   LOG_LEVEL or INFO.

    Returns:
        Configured logger instance.
    """
    level = log_level or os.getenv(
        "LOG_LEVEL", "INFO"
    )  # skip mypy as string always returned
    logger.setLevel(level)  # type: ignore[arg-type]
    return logger


def get_secret_value(secret_arn: str) -> str:
    """
    Fetch a secret string from AWS Secrets Manager.

    Args:
        secret_arn: The ARN of the secret to retrieve.

    Returns:
        The secret string value.

    Raises:
        ClientError: If the secret cannot be retrieved.
    """
    secretsmanager = boto3.client("secretsmanager")
    try:
        response = secretsmanager.get_secret_value(SecretId=secret_arn)
        return response["SecretString"]
    except ClientError as e:
        logger.exception(f"Error fetching secret {secret_arn}: {e}")
        raise


def validate_event_keys(event: dict[str, Any], required_keys: list[str]) -> None:
    """
    Validate that required keys are present in an event dictionary.

    Args:
        event: The event dictionary to validate.
        required_keys: List of keys that must be present.

    Raises:
        ValueError: If any required keys are missing.
    """
    missing_keys = [key for key in required_keys if key not in event]
    if missing_keys:
        error_msg = f"Missing required event keys: {missing_keys}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def validate_env_vars(required_vars: list[str]) -> dict[str, str]:
    """
    Validate that required environment variables are set.

    Args:
        required_vars: List of environment variable names required.

    Returns:
        Dictionary mapping variable names to their values.

    Raises:
        ValueError: If any required environment variables are missing.
    """
    env_dict = {}
    missing_vars = []

    for var_name in required_vars:
        value = os.getenv(var_name)
        if value is None:
            missing_vars.append(var_name)
        else:
            env_dict[var_name] = value

    if missing_vars:
        error_msg = f"Missing required environment variables: {missing_vars}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return env_dict
