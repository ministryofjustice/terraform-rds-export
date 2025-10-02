import os
import boto3
import logging
import pymssql
import pandas as pd
import awswrangler as wr

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
secretmanager = boto3.client("secretsmanager")


def safe_decode(val):
    """Attempt to decode bytes using CP1252, UTF-8, then Latin-1 as fallback."""
    if not isinstance(val, (bytes, bytearray)):
        return val
    for encoding in ("cp1252", "utf-8", "latin1"):
        try:
            return val.decode(encoding)
        except UnicodeDecodeError:
            continue
    logger.warning("Failed to decode bytes: %s", val.hex())
    return val.decode("cp1252", errors="replace")


def get_rowversion_cols(conn, table, schema="dbo"):
    """Return a set of colum names that are rowversion/timestamp for a given table."""
    sql = """
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        AND DATA_TYPE IN ('timestamp', 'rowversion')
    """

    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        return {row[0] for row in cur.fetchall()}


def get_secret_value(secret_arn: str) -> str:
    """Fetch secret string from Secrets Manager."""
    try:
        response = secretmanager.get_secret_value(SecretId=secret_arn)
        return response["SecretString"]
    except Exception:
        logger.exception("Error fetching secret: %s", secret_arn)
        raise


def decode_columns(df: pd.DataFrame, rowversion_cols: set) -> pd.DataFrame:
    """Decode binary columns to string."""
    for col in df.columns:
        non_nulls = df[col].dropna()
        if col in rowversion_cols:
            df[col] = df[col].map(lambda v: v.hex())
        elif not non_nulls.empty and isinstance(non_nulls.iloc[0], (bytes, bytearray)):
            logger.info(f"Decoding column '{col}' with fallback decoding")
            df[col] = df[col].apply(
                lambda x: safe_decode(x) if isinstance(x, (bytes, bytearray)) else x
            )
    return df


def handler(event, context):
    # === Environment & Event Variables ===
    db_endpoint = event["db_endpoint"]
    db_username = event["db_username"]
    db_pw_secret_arn = os.environ["DATABASE_PW_SECRET_ARN"]
    output_bucket = event["output_bucket"]
    database_refresh_mode = os.environ["DATABASE_REFRESH_MODE"]

    chunk = event["chunk"]
    db_name = chunk["database"]
    db_table = chunk["table"]
    db_query = chunk["query"]
    extraction_timestamp = chunk["extraction_timestamp"]

    # === Get Password ===
    db_password = get_secret_value(db_pw_secret_arn)

    # === Connect to SQL Server & Fetch Data ===
    try:
        logger.info(f"Connecting to {db_endpoint}, db: {db_name}, table: {db_table}")
        conn = pymssql.connect(
            server=db_endpoint,
            user=db_username,
            password=db_password,
            database=db_name,
            tds_version="7.4",
        )
        df = pd.read_sql_query(db_query, conn)
        logger.info(f"Fetched {len(df)} rows from {db_name}.{db_table}")
    except Exception as e:
        logger.exception(f"Failed to fetch data from SQL Server: {e}")
        raise

    # === Get rowversion and timestamp data type columns ===
    row_version_cols = get_rowversion_cols(conn, table=db_table, schema="dbo")
    logger.info(
        f"Columns with datatype 'timestamp' or 'rowversion' for {db_table}: {row_version_cols}"
    )

    # === Decode and Clean Data ===
    try:
        df = decode_columns(df, row_version_cols).astype(str)
        df["extraction_timestamp"] = extraction_timestamp
    except Exception as e:
        logger.exception(f"Failed during decoding or transformation: {e}")
        raise

    try:
        output_path = f"s3://{output_bucket}/{db_name}/{db_table}/"
        logger.info(
            f"Writing to S3: {output_path}"
            f"{' partitioned by extraction_timestamp' if database_refresh_mode == 'incremental' else ''}"
        )

        wr.s3.to_parquet(
            df=df,
            path=output_path,
            database=db_name,
            table=db_table,
            dataset=True,
            mode="append",
            partition_cols=(
                ["extraction_timestamp"]
                if database_refresh_mode == "incremental"
                else None
            ),
        )

        logger.info(f"Data export completed: {db_name}.{db_table} ({len(df)} rows)")
        return {"database": db_name, "table": db_table, "s3_output_path": output_path}

    except Exception as e:
        logger.exception(f"Failed to write to S3 for {db_name}.{db_table}: {e}")
        raise
