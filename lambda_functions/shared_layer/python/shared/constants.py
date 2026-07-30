"""Constants and configuration for Lambda functions."""

# Database configuration
DEFAULT_SCHEMA = "dbo"
ASPNET_PREFIX = "aspnet%"
ASPNET_VIEW_PREFIX = "vw_aspnet%"

# Data type constants
ROWVERSION_TYPES = {"timestamp", "rowversion"}
BINARY_TYPES = {bytes, bytearray}

# Encoding configuration
ENCODING_ATTEMPTS = ["cp1252", "utf-8", "latin1"]
ENCODING_FALLBACK = "cp1252"

# Environment variables
ENV_DATABASE_PW_SECRET_ARN = (
    "DATABASE_PW_SECRET_ARN"  # pragma: allowlist secret  # nosec
)
ENV_DATABASE_REFRESH_MODE = "DATABASE_REFRESH_MODE"
ENV_OUTPUT_BUCKET = "OUTPUT_BUCKET"
ENV_BACKUP_UPLOADS_BUCKET = "BACKUP_UPLOADS_BUCKET"
ENV_STATE_MACHINE_ARN = "STATE_MACHINE_ARN"
ENV_LOG_LEVEL = "LOG_LEVEL"

# Refresh modes
REFRESH_MODE_FULL = "full"
REFRESH_MODE_INCREMENTAL = "incremental"

# TDS configuration
TDS_VERSION = "7.4"
TDS_TIMEOUT = 5

# Athena configuration
ATHENA_RESULTS_PREFIX = "athena-results/"
ATHENA_WAIT_INTERVAL = 2

# S3 configuration
S3_ARN_FORMAT = "arn:aws:s3:::{}/"
S3_OBJECT_FORMAT = "{bucket}/{key}"

# SQL Server configuration
SQL_SERVER_ENGINE = "sqlserver-se"
SQL_SERVER_MASTER_DB = "master"

# Parquet/Iceberg configuration
PARQUET_TABLE_SUFFIX = ".parquet"
ICEBERG_PREFIX = "iceberg_"

# File types
BAK_FILE_EXTENSION = ".bak"

# Default values
DEFAULT_OUTPUT_PARQUET_FILE_SIZE = 10  # MiB
DEFAULT_MAX_CONCURRENCY = 5
