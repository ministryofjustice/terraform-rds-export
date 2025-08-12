import os
import boto3
import time
import logging
import pymssql
import pandas as pd
import tempfile
import warnings
import uuid
import awswrangler as wr

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable")

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager")
glue = boto3.client("glue")


def get_all_primary_keys(cursor, schema="dbo"):
    """
    Returns a dict mapping "schema.table" -> list of PK column names.
    Tables with no primary key will be present with an empty list.
    """
    # 1) Fetch all user tables in the schema (excluding aspnet%)
    cursor.execute(
        """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_SCHEMA = %s
          AND TABLE_NAME NOT LIKE 'aspnet%%'
    """,
        (schema,),
    )
    tables = cursor.fetchall()

    # 2) Fetch all PK columns in the schema
    cursor.execute(
        """
        SELECT
            s.name       AS schema_name,
            t.name       AS table_name,
            c.name       AS column_name,
            ic.key_ordinal
        FROM sys.indexes i
        JOIN sys.index_columns ic
          ON i.object_id = ic.object_id
         AND i.index_id  = ic.index_id
        JOIN sys.columns c
          ON ic.object_id = c.object_id
         AND ic.column_id = c.column_id
        JOIN sys.tables t
          ON i.object_id = t.object_id
        JOIN sys.schemas s
          ON t.schema_id = s.schema_id
        WHERE i.is_primary_key = 1
          AND s.name = %s
          AND t.name NOT LIKE 'aspnet%%'
        ORDER BY s.name, t.name, ic.key_ordinal
    """,
        (schema,),
    )
    pk_rows = cursor.fetchall()

    # 3) Initialize map with every table → empty list
    pk_map = {f"{sch}.{tbl}": [] for sch, tbl in tables}

    # 4) Populate PK columns
    for sch, tbl, col, _ in pk_rows:
        full = f"{sch}.{tbl}"
        pk_map[full].append(col)

    return pk_map


def get_table_stats(cursor, schema, table):
    full_table = f"{schema}.{table}"
    cursor.execute(f"EXEC sp_spaceused N'{full_table}'")
    result = cursor.fetchone()
    if result:
        row_count = int(result[1])
        data_size_kb = float(result[2].replace(" KB", "").replace(",", ""))
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
        df.to_parquet(tmp.name, engine="pyarrow", compression="snappy", index=False)
        parquet_size_kb = os.path.getsize(tmp.name) / 1024
        os.unlink(tmp.name)

    avg_row_size_kb = parquet_size_kb / len(df)
    rows_for_limit_parquet = int(1024 * 100 / avg_row_size_kb) if avg_row_size_kb else 0
    return avg_row_size_kb, rows_for_limit_parquet


def generate_chunk_query_by_rownum(
    schema, table, pk_columns, rows_per_chunk, chunk_index
):
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
    """

    # Normalize query to a flat one-liner
    return " ".join(query.strip().split())


def ensure_glue_database(glue_client, glue_db, description=None):
    db_input = {"Name": glue_db}
    if description:
        db_input["Description"] = description

    try:
        glue_client.create_database(DatabaseInput=db_input)
        logger.info("Created Glue database %s", glue_db)
    except glue_client.exceptions.AlreadyExistsException:
        logger.info("Glue database already exists: %s", glue_db)
    except Exception as e:
        logger.error("Error creating Glue database %s: %s", glue_db, e)
        raise


def map_sql_to_glue_type(sql_type: str) -> str:
    t = sql_type.lower()
    # logger.info(f"type: {t}")
    # map exact SQL bit → boolean
    if t == "bit":
        return "boolean"
    # map SQL integer types → int
    if any(t == i for i in ("tinyint", "smallint", "int", "bigint")):
        return "int"
    # map SQL floats → double
    if any(k in t for k in ("float", "real", "double")):
        return "double"
    # map SQL decimals → decimal
    if any(k in t for k in ("decimal", "numeric")):
        return "decimal"
    # map text types → string
    if any(k in t for k in ("char", "text")):
        return "string"
    # map dates/times → timestamp
    if any(k in t for k in ("date", "time")):
        return "timestamp"
    # default fallback
    return "string"


def create_glue_table(
    db_name: str, schema: str, table: str, glue_db: str, bucket: str, cursor
):
    # fetch column metadata
    cursor.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
    """,
        (schema, table),
    )
    cols = cursor.fetchall()
    # DONE: Fix column types
    # columns = [{"Name": cn, "Type": "string"} for cn, dt in cols]
    columns = [{"Name": cn, "Type": map_sql_to_glue_type(dt)} for cn, dt in cols]

    s3_path = f"s3://{bucket}/{db_name}/{schema}/{table}/"
    table_input = {
        "Name": table,
        "Description": f"Imported from {db_name}.{schema}.{table}",
        "StorageDescriptor": {
            "Columns": columns,
            "Location": s3_path,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "Compressed": False,
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {},
            },
        },
        "PartitionKeys": [{"Name": "extraction_timestamp", "Type": "string"}],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet"},
    }
    try:
        glue.create_table(DatabaseName=glue_db, TableInput=table_input)
        logger.info("Created Glue table %s.%s", glue_db, table)
    except glue.exceptions.AlreadyExistsException:
        logger.info("Glue table already exists: %s.%s", glue_db, table)
    except Exception as e:
        logger.error("Error creating Glue table %s.%s: %s", glue_db, table, e)


def handler(event, context):
    # Retrieve configuration from environment variables
    db_endpoint = event["db_endpoint"]
    db_pw_secret_arn = os.environ["DATABASE_PW_SECRET_ARN"]
    db_username = event["db_username"]
    db_name = event["db_name"]
    output_bucket = event["output_bucket"]
    extraction_timestamp = event["extraction_timestamp"]
    tables_to_export = event["tables_to_export"]

    # Check that the glue db exists, if not create it
    ensure_glue_database(glue, db_name, description=f"Catalog for {db_name}")

    # Fetch credentials from AWS Secrets Manager
    try:
        secret_response = secretmanager.get_secret_value(SecretId=db_pw_secret_arn)
        db_password = secret_response["SecretString"]
    except Exception as e:
        logger.error("Error fetching secret: %s", e)
        return

    time.sleep(0.5)

    try:
        conn = pymssql.connect(
            server=db_endpoint, user=db_username, password=db_password, database=db_name
        )
        query = """
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            p.rows AS original_row_count,
            '' AS exported_row_count,
            '' AS exported_timestamp
        FROM sys.tables t
        JOIN sys.indexes i ON t.object_id = i.object_id
        JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
        JOIN sys.allocation_units a ON p.partition_id = a.container_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE i.index_id <= 1
        GROUP BY s.name, t.name, p.rows
        """

        df = pd.read_sql_query(query, conn)

        # Log Table stats for all the schema
        logger.info("Table stats:\n%s", df.to_string(index=False))

        cursor = conn.cursor()

        # get all schemas
        cursor.execute(
            """
            SELECT name
            FROM sys.schemas
            WHERE name NOT IN ('sys', 'INFORMATION_SCHEMA')
        """
        )

        schemas = [row[0] for row in cursor.fetchall()]

        # collect primary keys from all schemas
        pk_map = {}
        for schema in schemas:
            try:
                pk_map.update(get_all_primary_keys(cursor, schema))
            except Exception as e:
                logger.warning(f"Failed to get PKs for schema {schema}: {e}")

        # Filter pk_map to supplied tables
        if tables_to_export:
            logger.info(f"Filtering pk_map for tables: {tables_to_export}")
            pk_map = {
                table: value
                for table, value in pk_map.items()
                if table in tables_to_export
            }
        else:
            logger.info("No tables_to_export provided — using all pk_map entries")

        # Create glue tables for each schema.table
        for full_table, pk_columns in pk_map.items():
            logger.info(f"Creating glue table for {full_table}")
            schema, table = full_table.split(".")
            create_glue_table(
                db_name,
                schema,
                table,
                glue_db=db_name,
                bucket=output_bucket,
                cursor=cursor,
            )
        if extraction_timestamp:
            df["extraction_timestamp"] = extraction_timestamp

        s3_path = f"s3://{output_bucket}/cafm/table-stats/"

        try:
            wr.s3.to_parquet(
                df=df,
                path=s3_path,
                dataset=True,
                mode="overwrite",
                database=db_name,
                table="table_stats",
                partition_cols=["extraction_timestamp"] if "extraction_timestamp" in df.columns else None,
                catalog_versioning=True
            )
            logger.info("Table stats written to S3 and Glue successfully.")
        except Exception as e:
            logger.error("Failed to write to S3/Glue: %s", e)
            raise

        chunks = []
        for full_table, pk_columns in pk_map.items():
            schema, table = full_table.split(".")
            rows, size_kb = get_table_stats(cursor, schema, table)

            # Calculate the number of chunks
            rows, size_kb = get_table_stats(cursor, schema, table)
            if not rows or rows == 0:
                logger.info(f"Skipping row size calculation: rows={rows}, table={table}")
                row_size_kb = 0
            else:
                row_size_kb = size_kb / rows

            parquet_row_kb, rows_for_limit_parquet = sample_parquet_size(
                conn, schema, table
            )
            num_chunks = (
                (rows + rows_for_limit_parquet - 1) // rows_for_limit_parquet
                if rows_for_limit_parquet
                else 1
            )

            logger.info("-" * 90)
            logger.info(
                f"{'Table':<40} {'Rows':>10} {'Chunks':>8} {'SQL KB/Row':>12} {'Parquet KB/Row':>16}"
            )
            logger.info(
                f"{full_table:<40} {rows:>10} {num_chunks:>8} {row_size_kb:>12.4f} {parquet_row_kb:>16.4f}"
            )
            logger.info("-" * 90)

            if rows == 0 or rows_for_limit_parquet == 0:
                continue

            if rows > 0 and not pk_columns:
                query = f"SELECT * FROM [{schema}].[{table}]"
                chunks.append(
                    {
                        "database": db_name,
                        "table": table,
                        "extraction_timestamp": extraction_timestamp,
                        "query": query,
                    }
                )
                # skip the PK-based sampling/partitioning below
                continue

            if rows == 0 or rows_for_limit_parquet == 0:
                continue

            for chunk_index in range(num_chunks):
                query = generate_chunk_query_by_rownum(
                    schema, table, pk_columns, rows_for_limit_parquet, chunk_index
                )
                chunk_info = {
                    "database": db_name,
                    "table": table,
                    "extraction_timestamp": extraction_timestamp,
                    "query": query,
                }
                chunks.append(chunk_info)

        # Close the cursor and connection
        cursor.close()
        logger.info(f"{len(chunks)} chunks to be processed")
        return {"chunks": chunks}
    except Exception as e:
        raise e
