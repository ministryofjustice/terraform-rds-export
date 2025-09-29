import os
import boto3
import time
import math
import logging
import pymssql
import pandas as pd
import warnings
import uuid
import awswrangler as wr
from urllib.parse import urlparse

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable")

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretmanager = boto3.client("secretsmanager", region_name=os.environ["REGION"])
glue = boto3.client("glue", region_name=os.environ["REGION"])
s3 = boto3.client("s3", region_name=os.environ["REGION"])
athena = boto3.client("athena", region_name=os.environ["REGION"])


def run_athena_query(query, database, workgroup):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    query_id = response["QueryExecutionId"]

    # Wait for completion
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break
        time.sleep(2)

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
        raise Exception(f"Athena query failed: {state} - {reason}")

    return query_id

def drop_table_and_data(database, table_name, bucket):
    """
    Deletes the Glue table entry and underlying S3 data for Iceberg tables.
    Athena DROP TABLE is not reliable for Iceberg — must use Glue API.
    """

    # 1. Delete Glue table (not via Athena)
    try:
        glue.delete_table(DatabaseName=database, Name=table_name)
        logger.info(f"Deleted Glue table: {database}.{table_name}")
    except glue.exceptions.EntityNotFoundException:
        logger.warning(f"Glue table not found: {database}.{table_name}")
    except Exception as e:
        logger.error(f"Failed to delete Glue table: {e}")
        raise

    # 2. Delete S3 objects in that location
    logger.info(f"Deleting all S3 objects for: s3://{bucket}/{table_name}/")
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=f"{table_name}/")

    deleted_count = 0
    for page in pages:
        if "Contents" in page:
            objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted_count += len(objects)

    logger.info(f"Deleted {deleted_count} objects from s3://{bucket}/{table_name}/")


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


def calculate_rows_per_chunk(row_count, size_kb, target_mb=10):
    try:
        row_count = int(row_count)
        size_kb = float(size_kb)
        if row_count == 0 or size_kb == 0:
            return 0.0, 0
        row_size_kb = size_kb / row_count
        rows_per_chunk = int((target_mb * 1024) / row_size_kb)
        return row_size_kb, rows_per_chunk
    except Exception as e:
        logger.error(f"Error in row size calculation: {e}")
        return 0.0, 0


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
    ORDER BY rn
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


def delete_glue_table(
    glue_db: str,
    table_name: str,
    database_refresh_mode: str,
    extraction_timestamp: str = None,
):
    try:
        # 1. Get Glue table location
        response = glue.get_table(DatabaseName=glue_db, Name=table_name)
        s3_path = response["Table"]["StorageDescriptor"]["Location"]
        logger.info(f"Table location: {s3_path}")

        # 2. Parse S3 path
        parsed = urlparse(s3_path)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")

        deleted_files = 0

        if database_refresh_mode == "full":
            logger.info("Performing FULL refresh: deleting entire table S3 prefix")
            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

            for page in pages:
                if "Contents" in page:
                    objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
                    deleted_files += len(objects)

        elif database_refresh_mode == "incremental":
            if not extraction_timestamp:
                raise ValueError(
                    "extraction_timestamp must be provided for incremental refresh."
                )

            partition_prefix = f"{prefix}/extraction_timestamp={extraction_timestamp}/"
            logger.info(
                f"Performing INCREMENTAL refresh: deleting partition folder {partition_prefix}"
            )

            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket, Prefix=partition_prefix)

            for page in pages:
                if "Contents" in page:
                    objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
                    deleted_files += len(objects)

        else:
            raise ValueError(
                f"Invalid database_refresh_mode: '{database_refresh_mode}'"
            )

        logger.info(f"Deleted {deleted_files} objects from s3://{bucket}/{prefix}")

        # 3. Delete Glue table (only for full refresh)
        if database_refresh_mode == "full":
            glue.delete_table(DatabaseName=glue_db, Name=table_name)
            logger.info(f"Deleted Glue table: {glue_db}.{table_name}")

        return {
            "status": "SUCCESS",
            "message": f"{'Deleted table and ' if database_refresh_mode == 'full' else ''}Deleted {deleted_files} files from {s3_path}",
        }

    except glue.exceptions.EntityNotFoundException:
        logger.warning(f"Table not found: {glue_db}.{table_name}")
        return {
            "status": "NOT_FOUND",
            "message": f"Glue table {glue_db}.{table_name} does not exist.",
        }

    except Exception as e:
        logger.error(f"Failed to delete Glue table or S3 data: {e}")
        return {"status": "ERROR", "message": str(e)}


def create_glue_table(
    database_refresh_mode: str,
    db_name: str,
    schema: str,
    table: str,
    glue_db: str,
    bucket: str,
    table_properties: dict,
    cursor,
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
    columns = [{"Name": cn, "Type": "string"} for cn, dt in cols]
    # columns = [{"Name": cn, "Type": map_sql_to_glue_type(dt)} for cn, dt in cols]

    s3_path = f"s3://{bucket}/{db_name}/{table}/"
    if database_refresh_mode == "incremental":
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
            "Parameters": table_properties,
        }
    else:
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
            "TableType": "EXTERNAL_TABLE",
            "Parameters": table_properties,
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
    database_refresh_mode = os.environ["DATABASE_REFRESH_MODE"]
    db_username = event["db_username"]
    db_name = event["db_name"]
    output_bucket = event["output_bucket"]
    extraction_timestamp = event["extraction_timestamp"]
    tables_to_export = event["tables_to_export"]
    output_parquet_file_size = float(os.environ["OUTPUT_PARQUET_FILE_SIZE"])

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
        query = f"""
        SELECT
            t.name AS table_name,
            p.rows AS original_row_count,
            NULL AS exported_row_count,
            '{extraction_timestamp}' AS extraction_timestamp
        FROM sys.tables t
        JOIN sys.indexes i ON t.object_id = i.object_id
        JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
        JOIN sys.allocation_units a ON p.partition_id = a.container_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE i.index_id <= 1
        GROUP BY s.name, t.name, p.rows
        """

        df = pd.read_sql_query(query, conn)
        logger.info("Table stats:\n%s", df.to_string(index=False))
        
        unique_tables = df['table_name'].unique()
        batch_size = 90
        num_batches = math.ceil(len(unique_tables) / batch_size)

        # Drop staging and main validation database tables
        for i in range(num_batches):
            staging_table_name = f"staging_table_export_validation_batch_{i}"
            drop_table_and_data(db_name, staging_table_name, output_bucket)
            
        drop_table_and_data(db_name, "staging_table_export_validation", output_bucket)
        drop_table_and_data(db_name, "table_export_validation", output_bucket)

        # Log Table stats for all the database tables
        create_query = f"""
            CREATE TABLE IF NOT EXISTS {db_name}.table_export_validation (
            table_name STRING,
            original_row_count BIGINT,
            exported_row_count BIGINT,
            extraction_timestamp STRING
            )
            PARTITIONED BY (table_name)
            LOCATION 's3://{output_bucket}/table_export_validation/'
            TBLPROPERTIES (
            'table_type' = 'ICEBERG',
            'format' = 'parquet'
            )
            """
        run_athena_query(create_query, db_name, workgroup="primary")
        logger.info("Ensured Iceberg table_export_validation exists.")

        columns_types = {
            "table_name": "string",
            "original_row_count": "bigint",
            "exported_row_count": "bigint",
            "extraction_timestamp": "string",
        }

        # 1. Extract unique table names and split into chunks

        for i in range(num_batches):
            batch_tables = unique_tables[i * batch_size: (i + 1) * batch_size]
            batch_df = df[df['table_name'].isin(batch_tables)]

            staging_table_name = f"staging_table_export_validation_batch_{i}"
            staging_path = f"s3://{output_bucket}/staging_table_export_validation/"

            logger.info(f"Processing batch {i+1}/{num_batches}: {len(batch_tables)} tables")

            # 2. Write batch to S3
            wr.s3.to_parquet(
                df=batch_df,
                path=staging_path,
                dataset=True,
                mode="overwrite"
            )

            # 3. Register as a Glue table
            wr.catalog.create_parquet_table(
                database=db_name,
                table=staging_table_name,
                path=staging_path,
                columns_types=columns_types,
                mode="overwrite"
            )

            # 4. Insert into Iceberg table using Athena
            insert_query = f"""
            INSERT INTO "{db_name}".table_export_validation
            SELECT * FROM "{db_name}".{staging_table_name}
            """
            run_athena_query(insert_query, db_name, workgroup="primary")

            logger.info(f"Inserted batch {i+1} successfully")


        conn = pymssql.connect(
            server=db_endpoint, user=db_username, password=db_password, database=db_name
        )

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
            table_prop = {
                "classification": "parquet",
                "source_primary_key": ", ".join(pk_columns),
                "extraction_key": "extraction_timestamp",
                "extraction_timestamp_column_name": "extraction_timestamp",
                "extraction_timestamp_column_dtype": "string",
            }
            schema, table = full_table.split(".")
            logger.info(f"Deleting glue table: {full_table}")
            delete_glue_table(
                glue_db=db_name,
                table_name=table,
                database_refresh_mode=database_refresh_mode,
            )
            logger.info(f"Creating glue table: {full_table}")
            create_glue_table(
                database_refresh_mode,
                db_name,
                schema,
                table,
                glue_db=db_name,
                bucket=output_bucket,
                table_properties=table_prop,
                cursor=cursor,
            )

        chunks = []
        for full_table, pk_columns in pk_map.items():
            schema, table = full_table.split(".")
            rows, size_kb = get_table_stats(cursor, schema, table)

            # Calculate the number of chunks
            rows, size_kb = get_table_stats(cursor, schema, table)
            if not rows or rows == 0:
                logger.info(
                    f"Skipping row size calculation: rows={rows}, table={table}"
                )
                row_size_kb = 0
            else:
                row_size_kb = size_kb / rows

            parquet_row_kb, rows_for_limit_parquet = calculate_rows_per_chunk(
                row_count=rows, size_kb=size_kb, target_mb=output_parquet_file_size
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
