import logging
import awswrangler as wr
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    db_name = event["db_name"]
    table_name = "table_export_validation"

    try:
        df = wr.athena.read_sql_table(table=table_name, database=db_name)
        logger.info(f"Loaded {len(df)} rows from {db_name}.{table_name}")

        # Convert rows to task dicts
        tasks = []
        for _, row in df.iterrows():
            tasks.append({
                "table_name": row["table_name"]
            })

        return { "tasks": tasks }

    except Exception as e:
        logger.error(f"Error preparing tasks: {str(e)}")
        raise e

