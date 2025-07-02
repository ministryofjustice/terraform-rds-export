

import os
import boto3
import json
import time
import logging
import pymssql
import pandas as pd
import tempfile
import warnings
import uuid

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable")

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")


def get_all_primary_keys(cursor, schema="dbo"):
    query = """
    SELECT
        s.name AS schema_name,
        t.name AS table_name,
        c.name AS column_name,
        ic.key_ordinal
    FROM sys.indexes i
    JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE i.is_primary_key = 1 
      AND s.name = %s
      AND t.name NOT LIKE 'aspnet%%'
    ORDER BY s.name, t.name, ic.key_ordinal
    """
    cursor.execute(query, (schema,))
    result = cursor.fetchall()
    pk_map = {}
    for schema_name, table_name, column_name, _ in result:
        full_table = f"{schema_name}.{table_name}"
        if full_table not in pk_map:
            pk_map[full_table] = []
        pk_map[full_table].append(column_name)
    return pk_map


def get_table_stats(cursor, schema, table):
    full_table = f"{schema}.{table}"
    cursor.execute(f"EXEC sp_spaceused N'{full_table}'")
    result = cursor.fetchone()
    if result:
        row_count = int(result[1])
        data_size_kb = float(result[2].replace(' KB', '').replace(',', ''))
        return row_count, data_size_kb
    return 0, 0.0


def sample_parquet_size(conn, schema, table, sample_rows=1000):
    query = f"SELECT TOP {sample_rows} * FROM [{schema}].[{table}]"
    df = pd.read_sql(query, conn)

    if df.empty:
        return 0.0, 0

    # Convert UUIDs to strings
    for col in df.select_dtypes(include="object"):
        if df[col].apply(lambda x: isinstance(x, uuid.UUID)).any():
            df[col] = df[col].astype(str)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as tmp:
        df.to_parquet(tmp.name, engine='pyarrow', compression='snappy', index=False)
        parquet_size_kb = os.path.getsize(tmp.name) / 1024
        os.unlink(tmp.name)

    avg_row_size_kb = parquet_size_kb / len(df)
    rows_for_1mb = int(1024 / avg_row_size_kb) if avg_row_size_kb else 0
    return avg_row_size_kb, rows_for_1mb


def generate_chunk_query_by_rownum(schema, table, pk_columns, rows_per_chunk, chunk_index):
    if not pk_columns:
        raise ValueError("Primary key column list cannot be empty.")

    order_clause = ", ".join(f"[{col}]" for col in pk_columns)
    full_table = f"[{schema}].[{table}]"

    start_row = chunk_index * rows_per_chunk + 1
    end_row = start_row + rows_per_chunk - 1

    query = f"""
    WITH Ordered AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY {order_clause}) AS rn
        FROM {full_table}
    )
    SELECT *
    FROM Ordered
    WHERE rn BETWEEN {start_row} AND {end_row}
    ORDER BY rn
    """

    # Normalize query to a flat one-liner
    return " ".join(query.strip().split())


def handler(event, context):
    print(event)
    # Retrieve configuration from environment variables
    db_endpoint = os.environ["DATABASE_ENDPOINT"]
    db_secret_arn = os.environ["DATABASE_SECRET_ARN"]
    db_name = event["db_name"]

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
        conn = pymssql.connect(server=db_endpoint, user=db_username,
                       password=db_password, database=db_name)
        cursor = conn.cursor()

        pk_map = get_all_primary_keys(cursor, "dbo")

        print(f"{'Table':<40} {'Rows':>10} {'Chunks':>8} {'SQL KB/Row':>12} {'Parquet KB/Row':>16}")
        print("-" * 90)

        chunks = []
        for full_table, pk_columns in pk_map.items():
            schema, table = full_table.split(".")
            rows, size_kb = get_table_stats(cursor, schema, table)
            row_size_kb = size_kb / rows if rows else 0
            parquet_row_kb, rows_for_limit_parquet = sample_parquet_size(conn, schema, table)


            if rows == 0 or rows_for_limit_parquet == 0:
                continue

            # Calculate the number of chunks
            num_chunks = (rows + rows_for_limit_parquet - 1) // rows_for_limit_parquet
            print(f"{full_table:<40} {rows:>10} {num_chunks:>8} {row_size_kb:>12.4f} {parquet_row_kb:>16.4f}")

            for chunk_index in range(num_chunks):
                query = generate_chunk_query_by_rownum(
                    schema, table, pk_columns, rows_for_limit_parquet, chunk_index
                )
                chunk_info = {
                    "database": db_name,
                    "schema": schema,
                    "table": table,
                    "chunk_index": chunk_index,
                    "rows_per_chunk": rows_for_limit_parquet,
                    "total_rows": rows,
                    "query": query,
                    "primary_keys": pk_columns,
                    "estimated_sql_kb_per_row": round(row_size_kb, 4),
                    "estimated_parquet_kb_per_row": round(parquet_row_kb, 4),
                }
                chunks.append(chunk_info)

        # Close the cursor and connection
        cursor.close()

        print(f"{len(chunks)} chunks to be processed")
        return {
            "chunks": chunks
        }

        # Close the connection
        connection.close()
    except Exception as e:
        logger.error("Error connecting to the database: %s", e)
