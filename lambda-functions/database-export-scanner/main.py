
import os
import boto3
import json
import time
import logging
from datetime import datetime
from sqlalchemy import create_engine, text

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")

def calculate_row_limit(current_rows, current_size_kb, target_size_gb):
    """
    Calculate the number of rows required to reach a target file size.

    Parameters:
      current_rows (int): Number of rows in the current dataset.
      current_size_kb (float): Total size of the current dataset in kilobytes (KB).
      target_size_gb (float): Desired target file size in gigabytes (GB).

    Returns:
      int: Approximate number of rows required to reach the target file size.
    """
    # Calculate the size per row in KB
    row_size_kb = current_size_kb / current_rows

    # Convert target size from GB to KB (1GB = 1024*1024 KB)
    target_size_kb = target_size_gb * 1024 * 1024

    # Calculate the row count
    row_limit = target_size_kb / row_size_kb
    return int(row_limit)


def split_table_tasks(schema, table, row_count, row_limit):
    """
    Splits a table extraction task into chunks based on row_count and row_limit.

    Parameters:
        schema (str): The schema name.
        table (str): The table name.
        row_count (int): Total number of rows in the table.
        row_limit (int): The maximum number of rows per chunk.

    Returns:
        list: A list of dictionaries where each dictionary contains:
              - schema: The schema name.
              - table: The table name.
              - row_start: The starting row index for the chunk.
              - row_end: The ending row index for the chunk.
    """
    tasks = []
    # Generate chunks: row_start begins at 0 and increases by row_limit each time.
    for row_start in range(0, row_count, row_limit):
        row_end = min(row_start + row_limit, row_count)
        tasks.append({
            "schema": schema,
            "table": table,
            "row_start": row_start,
            "row_end": row_end
        })
    return tasks


def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = os.environ["DATABASE_ENDPOINT"]
    db_secret_arn = os.environ["DATABASE_SECRET_ARN"]
    db_name = os.environ.get("DATABASE_NAME", "master")

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
        # Connect to the MS SQL Server database
        mssql_engine = create_engine(
            f"mssql+pymssql://{db_username}:{db_password}@{db_endpoint}:1433/restoredData20250319151623",
            # disable default reset-on-return scheme
            pool_reset_on_return=None,
        )
        # Create a connection
        connection = mssql_engine.connect()

        # Get a list of schema & tables in the database
        tables_sql = text("""
        DECLARE @sql NVARCHAR(MAX) = '';

        SELECT @sql = @sql + 
            'SELECT ''' + TABLE_SCHEMA + ''' AS TABLE_SCHEMA, ''' + TABLE_NAME + ''' AS TABLE_NAME ' +
            'UNION ALL '
        FROM INFORMATION_SCHEMA.TABLES;

        -- Remove the trailing " UNION ALL "
        SET @sql = LEFT(@sql, LEN(@sql) - 10);

        EXEC sp_executesql @sql;
        """)
        result = connection.execute(tables_sql)
        tables = [row for row in result]

        # Now, loop over each table and execute sp_spaceused to get the size (e.g., reserved space).
        chunks = []
        for schema, table in tables:
            sp_sql = text(f"EXEC sp_spaceused N'{schema}.{table}'")
            sp_result = connection.execute(sp_sql)
            sp_row = sp_result.fetchone()
            name, rows, reserved, data, index_size, unused = sp_row
            reserved = int(reserved.replace(" KB", ""))
            row_count = int(rows)
            row_limit = calculate_row_limit(row_count, reserved, 0.5) # Split into 1GB chunks

            logger.info("Table %s.%s has %s rows and %s KB reserved. Splitting into %s chunks.", schema, table, row_count, reserved, row_limit)
            chunks.extend([task for task in split_table_tasks(schema, table, row_count, row_limit)])


        return {
            "chunks": chunks
        }

        # Close the connection
        connection.close()
    except Exception as e:
        logger.error("Error connecting to the database: %s", e)
