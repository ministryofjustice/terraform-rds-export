"""Lambda function to export RDS database tables to Parquet files in S3."""

from typing import Any

import awswrangler as wr
import pandas as pd
import pymssql
from pymssql import Connection

from shared.constants import (
    DEFAULT_SCHEMA,
    ENCODING_ATTEMPTS,
    ENCODING_FALLBACK,
    ENV_DATABASE_PW_SECRET_ARN,
    ENV_DATABASE_REFRESH_MODE,
    REFRESH_MODE_INCREMENTAL,
    TDS_VERSION,
)
from shared.utils import configure_logging, get_secret_value, validate_env_vars

logger = configure_logging()


def safe_decode(val: bytes | bytearray) -> str:
    """
    Attempt to decode bytes using multiple encodings with fallback.

    Tries CP1252, UTF-8, and Latin-1 in sequence before falling back
    to CP1252 with replacement for unmappable characters.

    Args:
        val: Bytes or bytearray to decode.

    Returns:
        Decoded string value.
    """
    if not isinstance(val, (bytes, bytearray)):
        return val

    for encoding in ENCODING_ATTEMPTS:
        try:
            return val.decode(encoding)
        except UnicodeDecodeError:
            continue

    logger.warning(f"Failed to decode bytes: {val.hex()}")
    return val.decode(ENCODING_FALLBACK, errors="replace")


def get_rowversion_cols(
    conn: Connection, table: str, schema: str = DEFAULT_SCHEMA
) -> set[str]:
    """
    Retrieve column names that are rowversion or timestamp data types.

    Args:
        conn: pymssql connection object.
        table: Table name to query.
        schema: Database schema (default: dbo).

    Returns:
        Set of column names with rowversion/timestamp data type.
    """
    sql = """
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        AND DATA_TYPE IN ('timestamp', 'rowversion')
    """

    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        return {row[0] for row in cur.fetchall()}


def decode_columns(df: pd.DataFrame, rowversion_cols: set[str]) -> pd.DataFrame:
    """
    Decode binary columns to string representation.

    Rowversion/timestamp columns are converted to hex strings. Other binary
    columns are decoded using safe_decode with multiple encoding attempts.

    Args:
        df: DataFrame with potentially binary columns.
        rowversion_cols: Set of column names containing rowversion data.

    Returns:
        DataFrame with binary columns converted to strings.
    """
    for col in df.columns:
        non_nulls = df[col].dropna()

        if col in rowversion_cols:
            df[col] = df[col].map(lambda v: v.hex() if v is not None else None)
        elif not non_nulls.empty and isinstance(non_nulls.iloc[0], (bytes, bytearray)):
            logger.info(f"Decoding column '{col}' with fallback decoding")
            df[col] = df[col].apply(
                lambda x: safe_decode(x) if isinstance(x, (bytes, bytearray)) else x
            )

    return df


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Lambda handler to export a database table to Parquet format.

    Retrieves table data from SQL Server via the provided query, handles
    binary column decoding, and exports to S3 in Parquet format with
    optional partitioning by extraction timestamp.

    Args:
        event: Lambda event containing:
            - db_endpoint: RDS endpoint address
            - db_username: Database username
            - output_bucket: S3 bucket for Parquet output
            - extraction_timestamp: Timestamp for partitioning
            - chunk: Dict with database, table, and query
        context: Lambda context object.

    Returns:
        Dict with database, table, and S3 output path.

    Raises:
        ValueError: If required event keys or environment variables are missing.
        pymssql.Error: If database connection or query fails.
        Exception: If data transformation or S3 write fails.
    """
    # Validate required environment variables
    try:
        env_vars = validate_env_vars(
            [ENV_DATABASE_PW_SECRET_ARN, ENV_DATABASE_REFRESH_MODE]
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    # Extract event parameters
    db_endpoint = event["db_endpoint"]
    db_username = event["db_username"]
    output_bucket = event["output_bucket"]
    extraction_timestamp = event["extraction_timestamp"]
    chunk = event["chunk"]

    db_name = chunk["database"]
    db_table = chunk["table"]
    db_query = chunk["query"]

    db_password = get_secret_value(env_vars[ENV_DATABASE_PW_SECRET_ARN])
    refresh_mode = env_vars[ENV_DATABASE_REFRESH_MODE]

    # Connect to SQL Server and fetch data
    try:
        logger.info(f"Connecting to {db_endpoint}, db: {db_name}, table: {db_table}")
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version=TDS_VERSION,
        )
        df = pd.read_sql_query(db_query, conn)
        logger.info(f"Fetched {len(df)} rows from {db_name}.{db_table}")
        conn.close()
    except Exception as e:
        logger.exception(f"Failed to fetch data from SQL Server: {e}")
        raise

    # Get rowversion columns and decode binary data
    try:
        row_version_cols = get_rowversion_cols(
            conn, table=db_table, schema=DEFAULT_SCHEMA
        )
        logger.info(
            f"Columns with rowversion/timestamp for {db_table}: {row_version_cols}"
        )

        df = decode_columns(df, row_version_cols).astype(str)
        df["extraction_timestamp"] = extraction_timestamp
    except Exception as e:
        logger.exception(f"Failed during decoding or transformation: {e}")
        raise

    # Write to S3 in Parquet format
    try:
        output_path = f"s3://{output_bucket}/{db_name}/{db_table}/"
        partition_info = (
            " partitioned by extraction_timestamp"
            if refresh_mode == REFRESH_MODE_INCREMENTAL
            else ""
        )
        logger.info(f"Writing to S3: {output_path}{partition_info}")

        wr.s3.to_parquet(
            df=df,
            path=output_path,
            database=db_name,
            table=db_table,
            dataset=True,
            mode="append",
            partition_cols=(
                ["extraction_timestamp"]
                if refresh_mode == REFRESH_MODE_INCREMENTAL
                else None
            ),
        )

        logger.info(f"Data export completed: {db_name}.{db_table} ({len(df)} rows)")
        return {
            "database": db_name,
            "table": db_table,
            "s3_output_path": output_path,
        }

    except Exception as e:
        logger.exception(f"Failed to write to S3 for {db_name}.{db_table}: {e}")
        raise
