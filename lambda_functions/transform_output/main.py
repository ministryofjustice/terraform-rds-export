"""Lambda function to transform and deduplicate export output."""

from typing import Any

from shared.utils import configure_logging

logger = configure_logging()


def get_unique(
    data: list[dict[str, Any]], keys_to_keep: list[str]
) -> list[dict[str, Any]]:
    """
    Deduplicate a list of dictionaries based on specified keys.

    Creates unique tuples of key-value pairs and converts back to dictionaries,
    effectively removing duplicate entries while preserving specified fields.

    Args:
        data: List of dictionaries to deduplicate.
        keys_to_keep: List of keys to extract for uniqueness comparison.

    Returns:
        List of unique dictionaries containing only specified keys.
    """
    unique_tuples = {tuple((k, d[k]) for k in keys_to_keep) for d in data}
    return [dict(t) for t in unique_tuples]


def handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, Any]]]:
    """
    Lambda handler to transform export output into deduplicated format.

    Receives a list of export chunks (table export results) and returns
    a deduplicated list containing only database and table names. This
    reduces data size for downstream processing steps.

    Args:
        event: Lambda event containing:
            - chunks: List of dicts with database/table/timestamp info
        context: Lambda context object.

    Returns:
        Dict containing list of unique table definitions.

    Example:
        Input: {"chunks": [
            {"database": "db1", "table": "tbl1", "s3_path": "..."},
            {"database": "db1", "table": "tbl1", "s3_path": "..."},
            {"database": "db1", "table": "tbl2", "s3_path": "..."}
        ]}
        Output: {"tables": [
            {"database": "db1", "table": "tbl1"},
            {"database": "db1", "table": "tbl2"}
        ]}
    """
    data = event["chunks"]
    keys_to_keep = ["database", "table"]

    logger.info(
        f"Deduplicating {len(data)} export chunks for {len(keys_to_keep)} unique keys"
    )
    result = get_unique(data=data, keys_to_keep=keys_to_keep)
    logger.info(f"Deduplication complete: {len(result)} unique tables")

    return {"tables": result}
