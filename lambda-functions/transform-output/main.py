import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

def handler(event, context):
    data = event["chunks"]
    name = event["name"]
    environment = event["environment"]

    # Choose which keys to keep
    keys_to_keep = ["database", "table", "extraction_timestamp"]

    # Lambda to filter and deduplicate
    get_unique = lambda lst: [
        dict(t)
        for t in {tuple((k, d[k]) for k in keys_to_keep) for d in lst}
    ]

    result = get_unique(data)

    return {
        "name": name,
        "environment": environment,
        "tables": result
    }