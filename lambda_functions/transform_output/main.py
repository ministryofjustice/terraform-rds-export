import logging
import os

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


# Filter and deduplicate data
def get_unique(data: list[dict], keys_to_keep: list):
    if not all(k in d for d in data for k in keys_to_keep):
        raise KeyError("One or more required keys missing")

    unique_tuples = {tuple((k, d[k]) for k in keys_to_keep) for d in data}

    return [dict(t) for t in unique_tuples]


# Transforms the output to keep minimal info as input for next step
def handler(event, context):
    data = event["chunks"]

    # Choose which keys to keep
    keys_to_keep = ["database", "table"]

    result = get_unique(data=data, keys_to_keep=keys_to_keep)

    return {"tables": result}
