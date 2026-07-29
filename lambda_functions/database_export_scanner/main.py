"""Lambda function to scan database schema and generate export chunks."""

import math
import os
import time
import warnings
from typing import Any
from urllib.parse import urlparse

import awswrangler as wr
import boto3
import pandas as pd
import pymssql
from pymssql import Cursor

from shared.constants import (
    ASPNET_PREFIX,
    DEFAULT_SCHEMA,
    ENV_DATABASE_PW_SECRET_ARN,
    ENV_DATABASE_REFRESH_MODE,
    ENV_OUTPUT_BUCKET,
    REFRESH_MODE_INCREMENTAL,
    REFRESH_MODE_FULL,
    TDS_VERSION,
)
from shared.utils import (
    configure_logging,
    get_secret_value,
    validate_env_vars,
    validate_event_keys,
)

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable")

logger = configure_logging()
glue = boto3.client("glue")
s3 = boto3.client("s3")
athena = boto3.client("athena")

# Table names for staging and validation
VALIDATION_TABLE = "table_export_validation"
STAGING_TABLE_PREFIX = "staging_table_export_validation"

# Glue table configuration
PARQUET_INPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
PARQUET_OUTPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
PARQUET_SERDE = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"

# Default batch size for table processing
DEFAULT_BATCH_SIZE = 90


def run_athena_query(query: str, database: str, bucket: str) -> str:
    """
    Execute an Athena query and wait for completion.

    Args:
        query: SQL query string.
        database: Athena database name.
        bucket: S3 bucket for result location.

    Returns:
        Query execution ID.

    Raises:
        Exception: If query fails.
    """
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": f"s3://{bucket}/athena-results/"},
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
        error_msg = f"Athena query failed: {state} - {reason}"
        logger.error(error_msg)
        raise Exception(error_msg)

    return query_id


def drop_table_and_data(database: str, table_name: str, bucket: str) -> None:
    """
    Delete Glue table and underlying S3 data for Iceberg tables.

    Uses Glue API for table deletion rather than Athena, as Athena DROP TABLE
    is unreliable for Iceberg format.

    Args:
        database: Glue database name.
        table_name: Table name to delete.
        bucket: S3 bucket containing table data.

    Raises:
        Exception: If Glue table deletion fails.
    """
    # Delete Glue table entry
    try:
        glue.delete_table(DatabaseName=database, Name=table_name)
        logger.info(f"Deleted Glue table: {database}.{table_name}")
    except glue.exceptions.EntityNotFoundException:
        logger.warning(f"Glue table not found: {database}.{table_name}")
    except Exception as e:
        logger.error(f"Failed to delete Glue table: {e}")
        raise

    # Delete S3 objects
    logger.info(f"Deleting S3 objects for: s3://{bucket}/{table_name}/")
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=f"{table_name}/")

    deleted_count = 0
    for page in pages:
        if "Contents" in page:
            objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted_count += len(objects)

    logger.info(f"Deleted {deleted_count} objects from s3://{bucket}/{table_name}/")


def get_all_primary_keys(
    cursor: Cursor, schema: str = DEFAULT_SCHEMA
) -> dict[str, list[str]]:
    """
    Retrieve primary key information for all user tables in a schema.

    Returns a dictionary mapping "schema.table" to list of PK column names.
    Tables without primary keys will have empty lists.

    Args:
        cursor: Database cursor.
        schema: Database schema name (default: dbo).

    Returns:
        Dictionary mapping full table names to primary key columns.
    """
    # Fetch all user tables
    cursor.execute(
        """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_SCHEMA = %s
          AND TABLE_NAME NOT LIKE %s
        """,
        (schema, ASPNET_PREFIX),
    )
    tables = cursor.fetchall()

    # Fetch all primary key columns
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
          AND t.name NOT LIKE %s
        ORDER BY s.name, t.name, ic.key_ordinal
        """,
        (schema, ASPNET_PREFIX),
    )
    pk_rows = cursor.fetchall()

    # Initialize map with every table
    pk_map: dict[str, list[str]] = {f"{sch}.{tbl}": [] for sch, tbl in tables}

    # Populate PK columns
    for sch, tbl, col, _ in pk_rows:
        full = f"{sch}.{tbl}"
        pk_map[full].append(col)

    logger.info(f"Retrieved primary keys for {len(pk_map)} tables in schema {schema}")
    return pk_map


def get_table_stats(cursor: Cursor, schema: str, table: str) -> tuple[int, float]:
    """
    Get row count and size statistics for a table.

    Args:
        cursor: Database cursor.
        schema: Schema name.
        table: Table name.

    Returns:
        Tuple of (row_count, size_in_kb).
    """
    full_table = f"{schema}.{table}"
    cursor.execute(f"EXEC sp_spaceused N'{full_table}'")
    result = cursor.fetchone()
    if result:
        row_count = int(result[1])
        data_size_kb = float(str(result[2]).replace(" KB", "").replace(",", ""))
        return row_count, data_size_kb
    return 0, 0.0


def calculate_rows_per_chunk(
    row_count: int, size_kb: float, target_mb: int = 10
) -> tuple[float, int]:
    """
    Calculate optimal rows per chunk based on target file size.

    Args:
        row_count: Number of rows in table.
        size_kb: Current size in kilobytes.
        target_mb: Target output file size in MB.

    Returns:
        Tuple of (row_size_kb, rows_per_chunk).
    """
    try:
        row_count = int(row_count)
        size_kb = float(size_kb)

        if row_count == 0 or size_kb == 0:
            return 0.0, 0

        row_size_kb = size_kb / row_count
        rows_per_chunk = int((target_mb * 1024) / row_size_kb)
        return row_size_kb, rows_per_chunk

    except Exception as e:
        logger.error(f"Error calculating rows per chunk: {e}")
        return 0.0, 0


def generate_chunk_query_by_rownum(
    schema: str,
    table: str,
    pk_columns: list[str],
    rows_per_chunk: int,
    chunk_index: int,
) -> str:
    """
    Generate SQL query to extract a chunk of rows using row numbers.

    Uses ROW_NUMBER() window function ordered by primary key to partition
    large tables into manageable export chunks.

    Args:
        schema: Schema name.
        table: Table name.
        pk_columns: List of primary key columns.
        rows_per_chunk: Number of rows per chunk.
        chunk_index: Zero-based chunk number.

    Returns:
        SQL query string for the chunk.

    Raises:
        ValueError: If pk_columns is empty.
    """
    if not pk_columns:
        raise ValueError("Primary key column list cannot be empty")

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

    # Flatten to single line
    return " ".join(query.strip().split())


def ensure_glue_database(
    glue_client: Any, db_name: str, description: str | None = None
) -> None:
    """
    Ensure a Glue database exists, creating it if necessary.

    Args:
        glue_client: Glue client.
        db_name: Database name.
        description: Optional database description.

    Raises:
        Exception: If database creation fails (except AlreadyExistsException).
    """
    db_input = {"Name": db_name}
    if description:
        db_input["Description"] = description

    try:
        glue_client.create_database(DatabaseInput=db_input)
        logger.info(f"Created Glue database: {db_name}")
    except glue_client.exceptions.AlreadyExistsException:
        logger.info(f"Glue database already exists: {db_name}")
    except Exception as e:
        logger.error(f"Error creating Glue database {db_name}: {e}")
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


def delete_glue_table_and_data(
    glue_db: str,
    table_name: str,
    database_refresh_mode: str,
) -> dict[str, str]:
    """
    Delete Glue table and optionally its S3 data.

    Args:
        glue_db: Glue database name.
        table_name: Table name.
        database_refresh_mode: "full" or "incremental".

    Returns:
        Status dictionary with result information.
    """
    try:
        # Get table location
        response = glue.get_table(DatabaseName=glue_db, Name=table_name)
        s3_path = response["Table"]["StorageDescriptor"]["Location"]
        logger.info(f"Table location: {s3_path}")

        # Parse S3 path
        parsed = urlparse(s3_path)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")

        deleted_files = 0

        if database_refresh_mode == REFRESH_MODE_FULL:
            logger.info("Performing FULL refresh: deleting entire table S3 prefix")
            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

            for page in pages:
                if "Contents" in page:
                    objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
                    deleted_files += len(objects)

            logger.info(f"Deleted {deleted_files} objects from s3://{bucket}/{prefix}")

            # Delete Glue table (only for full refresh)
            glue.delete_table(DatabaseName=glue_db, Name=table_name)
            logger.info(f"Deleted Glue table: {glue_db}.{table_name}")

            return {
                "status": "SUCCESS",
                "message": f"Deleted glue table and {deleted_files} files from {s3_path}",
            }
        else:
            # Incremental mode: preserve table, skip S3 deletion
            logger.info("Performing INCREMENTAL refresh: preserving table and S3 data")
            return {
                "status": "SUCCESS",
                "message": f"Preserved glue table {glue_db}.{table_name} for incremental refresh",
            }

    except glue.exceptions.EntityNotFoundException:
        logger.warning(f"Table not found: {glue_db}.{table_name}")
        return {
            "status": "NOT_FOUND",
            "message": f"Glue table {glue_db}.{table_name} does not exist",
        }

    except Exception as e:
        logger.error(f"Failed to delete Glue table or S3 data: {e}")
        return {"status": "ERROR", "message": str(e)}


def sort_cols(cols: list[dict[str, str]], field: str) -> list[dict[str, str]]:
    """Sort column list by specified field."""
    cols_conv = [{k.capitalize(): v.lower() for k, v in col.items()} for col in cols]
    return sorted(cols_conv, key=lambda c: c[field.capitalize()])


def is_not_rn(column: dict[str, str]) -> bool:
    """Check if column name is not 'rn' (row number)."""
    return column.get("Name", "").lower() != "rn"


def create_glue_table(
    database_refresh_mode: str,
    db_name: str,
    schema: str,
    table: str,
    glue_db: str,
    bucket: str,
    table_properties: dict[str, str],
    cursor: Cursor,
) -> None:
    """
    Create or update a Glue table for a database table.

    Creates external Parquet table with appropriate metadata and schema
    information. For incremental mode, adds extraction_timestamp partitioning.

    Args:
        database_refresh_mode: "full" or "incremental".
        db_name: Source database name.
        schema: Schema name.
        table: Table name.
        glue_db: Glue database name.
        bucket: S3 bucket for data.
        table_properties: Table-level properties metadata.
        cursor: Database cursor for schema inspection.

    Raises:
        Exception: If table creation fails.
    """
    # Fetch column metadata
    cursor.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        """,
        (schema, table),
    )
    cols = cursor.fetchall()
    columns = [{"Name": cn, "Type": "string"} for cn, _dt in cols]

    # Add extraction_timestamp for full mode
    if database_refresh_mode == REFRESH_MODE_FULL:
        columns.append({"Name": "extraction_timestamp", "Type": "string"})

    s3_path = f"s3://{bucket}/{db_name}/{table}/"

    # Build table input based on refresh mode
    table_input: dict[str, Any] = {
        "Name": table,
        "Description": f"Imported from {db_name}.{schema}.{table}",
        "StorageDescriptor": {
            "Columns": columns,
            "Location": s3_path,
            "InputFormat": PARQUET_INPUT_FORMAT,
            "OutputFormat": PARQUET_OUTPUT_FORMAT,
            "Compressed": False,
            "SerdeInfo": {
                "SerializationLibrary": PARQUET_SERDE,
                "Parameters": {},
            },
        },
        "TableType": "EXTERNAL_TABLE",
        "Parameters": table_properties,
    }

    if database_refresh_mode == REFRESH_MODE_INCREMENTAL:
        table_input["PartitionKeys"] = [
            {"Name": "extraction_timestamp", "Type": "string"},
        ]

    try:
        glue.create_table(DatabaseName=glue_db, TableInput=table_input)
        logger.info(f"Created Glue table: {glue_db}.{table}")

    except glue.exceptions.AlreadyExistsException:
        # Check if metadata needs updating
        response = glue.get_table(DatabaseName=glue_db, Name=table)
        old_columns_glue = response["Table"]["StorageDescriptor"]["Columns"]
        old_columns = [col for col in old_columns_glue if is_not_rn(col)]

        if sort_cols(columns, "Name") != sort_cols(old_columns, "Name"):
            glue.update_table(DatabaseName=glue_db, TableInput=table_input)
            logger.info(
                "Glue table already exists: %s.%s. Metadata updated.", glue_db, table
            )
        else:
            logger.info(f"Glue table already exists: {glue_db}.{table}")

    except Exception as e:
        logger.error(f"Error creating Glue table {glue_db}.{table}: {e}")
        raise


def handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, Any]]]:
    """
    Lambda handler to scan database and generate export chunks.

    Analyzes database schema, creates Glue metadata tables, calculates optimal
    partitioning, and generates queries for exporting each chunk to S3.

    Args:
        event: Lambda event containing:
            - db_endpoint: RDS endpoint
            - db_username: Database username
            - db_name: Database name
            - extraction_timestamp: Extraction timestamp
            - output_bucket: S3 bucket for output
            - tables_to_export: Optional list of specific tables
        context: Lambda context object.

    Returns:
        Dict with list of export chunks, each containing database, table, and query.

    Raises:
        ValueError: If required event keys or environment variables are missing.
        Exception: If database operations fail.
    """
    # Validate event structure
    try:
        validate_event_keys(
            event,
            [
                "db_endpoint",
                "db_username",
                "db_name",
                "extraction_timestamp",
                "output_bucket",
            ],
        )
    except ValueError as e:
        logger.error(f"Invalid event structure: {e}")
        raise

    # Validate environment variables
    try:
        env_vars = validate_env_vars(
            [
                ENV_DATABASE_PW_SECRET_ARN,
                ENV_DATABASE_REFRESH_MODE,
                ENV_OUTPUT_BUCKET,
            ]
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    # Extract parameters
    db_endpoint = event["db_endpoint"]
    db_username = event["db_username"]
    db_name = event["db_name"]
    extraction_timestamp = event["extraction_timestamp"]
    output_bucket = env_vars[ENV_OUTPUT_BUCKET]
    tables_to_export = event.get("tables_to_export")
    database_refresh_mode = env_vars[ENV_DATABASE_REFRESH_MODE]
    output_parquet_file_size = float(os.environ.get("OUTPUT_PARQUET_FILE_SIZE", "10"))

    db_password = get_secret_value(env_vars[ENV_DATABASE_PW_SECRET_ARN])

    # Ensure Glue database exists
    ensure_glue_database(glue, db_name, description=f"Catalog for {db_name}")

    time.sleep(0.5)

    try:
        # Connect and fetch table statistics
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version=TDS_VERSION,
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
        logger.info(f"Table statistics:\n{df.to_string(index=False)}")

        unique_tables = df["table_name"].unique()
        batch_size = DEFAULT_BATCH_SIZE
        num_batches = math.ceil(len(unique_tables) / batch_size)

        # Clean up staging and validation tables
        for i in range(num_batches):
            staging_table_name = f"{STAGING_TABLE_PREFIX}_batch_{i}"
            drop_table_and_data(db_name, staging_table_name, output_bucket)

        drop_table_and_data(db_name, STAGING_TABLE_PREFIX, output_bucket)
        drop_table_and_data(db_name, VALIDATION_TABLE, output_bucket)

        # Create Athena Iceberg validation table
        create_query = f"""
            CREATE TABLE IF NOT EXISTS "{db_name}"."{VALIDATION_TABLE}" (
                table_name STRING,
                original_row_count BIGINT,
                exported_row_count BIGINT,
                extraction_timestamp STRING
            )
            PARTITIONED BY (table_name)
            LOCATION 's3://{output_bucket}/{VALIDATION_TABLE}/'
            TBLPROPERTIES (
                'table_type' = 'ICEBERG',
                'format' = 'parquet'
            )
        """
        run_athena_query(create_query, db_name, output_bucket)
        logger.info(f"Ensured Iceberg {VALIDATION_TABLE} table exists")

        columns_types = {
            "table_name": "string",
            "original_row_count": "bigint",
            "exported_row_count": "bigint",
            "extraction_timestamp": "string",
        }

        # Process table statistics in batches
        for i in range(num_batches):
            batch_tables = unique_tables[i * batch_size : (i + 1) * batch_size]
            batch_df = df[df["table_name"].isin(batch_tables)]

            staging_table_name = f"{STAGING_TABLE_PREFIX}_batch_{i}"
            staging_path = f"s3://{output_bucket}/{STAGING_TABLE_PREFIX}/"

            logger.info(
                f"Processing batch {i + 1}/{num_batches}: {len(batch_tables)} tables"
            )

            # Write batch to S3
            wr.s3.to_parquet(
                df=batch_df, path=staging_path, dataset=True, mode="overwrite"
            )

            # Register as Glue table
            wr.catalog.create_parquet_table(
                database=db_name,
                table=staging_table_name,
                path=staging_path,
                columns_types=columns_types,
                mode="overwrite",
            )

            # Insert into Iceberg table
            insert_query = f"""
                INSERT INTO "{db_name}"."{VALIDATION_TABLE}"
                SELECT * FROM "{db_name}"."{staging_table_name}"
            """
            run_athena_query(insert_query, db_name, output_bucket)
            logger.info(f"Inserted batch {i + 1} successfully")

        # Reconnect for schema analysis
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version=TDS_VERSION,
        )
        cursor = conn.cursor()

        # Get all schemas
        cursor.execute(
            """
            SELECT name
            FROM sys.schemas
            WHERE name NOT IN ('sys', 'INFORMATION_SCHEMA')
            """
        )
        schemas = [row[0] for row in cursor.fetchall()]

        # Collect primary keys from all schemas
        pk_map = {}
        for schema in schemas:
            try:
                pk_map.update(get_all_primary_keys(cursor, schema))
            except Exception as e:
                logger.warning(f"Failed to get PKs for schema {schema}: {e}")

        # Filter to requested tables if specified
        if tables_to_export:
            logger.info(f"Filtering tables for export: {tables_to_export}")
            pk_map = {
                table: value
                for table, value in pk_map.items()
                if table in tables_to_export
            }
        else:
            logger.info("No table filter specified; using all tables")

        # Create Glue tables and generate export chunks
        chunks = []

        for full_table, pk_columns in pk_map.items():
            table_prop = {
                "classification": "parquet",
                "source_primary_key": ", ".join(pk_columns),
                "extraction_key": "extraction_timestamp",
                "extraction_timestamp_column_name": "extraction_timestamp",
                "extraction_timestamp_column_dtype": "string",
            }

            schema, table = full_table.split(".")

            delete_glue_table_and_data(
                glue_db=db_name,
                table_name=table,
                database_refresh_mode=database_refresh_mode,
            )

            logger.info(f"Creating Glue table: {full_table}")
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

            # Calculate chunking strategy
            rows, size_kb = get_table_stats(cursor, schema, table)

            if rows == 0:
                logger.info("Skipping chunking for empty table: %s.%s", schema, table)
                continue

            row_size_kb, rows_for_limit_parquet = calculate_rows_per_chunk(
                row_count=rows, size_kb=size_kb, target_mb=int(output_parquet_file_size)
            )

            num_chunks = (
                (rows + rows_for_limit_parquet - 1) // rows_for_limit_parquet
                if rows_for_limit_parquet
                else 1
            )

            logger.info(
                "%-40s %10d rows, %8d chunks, %12.4f KB/row, %16.4f KB/parquet",
                full_table,
                rows,
                num_chunks,
                row_size_kb,
                row_size_kb * rows_for_limit_parquet / 1024
                if rows_for_limit_parquet
                else 0,
            )

            # Generate chunks
            if pk_columns:
                # Use PK-based chunking
                for chunk_index in range(num_chunks):
                    query = generate_chunk_query_by_rownum(
                        schema, table, pk_columns, rows_for_limit_parquet, chunk_index
                    )
                    chunks.append(
                        {
                            "database": db_name,
                            "table": table,
                            "extraction_timestamp": extraction_timestamp,
                            "query": query,
                        }
                    )
            else:
                # No PK; export entire table as single chunk
                query = f"SELECT * FROM [{schema}].[{table}]"
                chunks.append(
                    {
                        "database": db_name,
                        "table": table,
                        "extraction_timestamp": extraction_timestamp,
                        "query": query,
                    }
                )

        cursor.close()
        conn.close()

        logger.info(f"Generated {len(chunks)} export chunks for processing")
        return {"chunks": chunks}

    except Exception as e:
        logger.exception(f"Error during database scan: {e}")
        raise
