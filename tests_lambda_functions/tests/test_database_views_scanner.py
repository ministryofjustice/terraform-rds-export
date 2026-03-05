import importlib
import pytest
import boto3
import os
import pandas as pd
import sys
import types


@pytest.fixture
def module_under_test():
    fake_pymssql = types.ModuleType("pymssql")
    fake_pymssql.connect = lambda **kwargs: object()
    sys.modules["pymssql"] = fake_pymssql

    module = importlib.import_module("lambda_functions.database_views_scanner.main")
    module = importlib.reload(module)
    return module


@pytest.fixture
def event():
    return {
        "db_endpoint": "db.example.local",
        "db_username": "db_user",
        "db_name": "test_db",
        "extraction_timestamp": "2026-02-26T12:00:00",
        "output_bucket": "test-output-bucket",
    }


def _create_secret(secret_string="test-password"):
    secretsmanager = boto3.client("secretsmanager", region_name="eu-west-2")
    response = secretsmanager.create_secret(
        Name="database-views-scanner-secret",
        SecretString=secret_string,
    )
    return response["ARN"]


def test_get_secret_value(module_under_test):
    """Returns secret string from Secrets Manager."""

    secret_arn = _create_secret("my-password")

    assert module_under_test.get_secret_value(secret_arn) == "my-password"


def test_handler_successful_run(event, module_under_test):
    """Extracts view definitions and writes parquet output to S3."""

    s3 = boto3.client("s3", region_name="eu-west-2")
    s3.create_bucket(
        Bucket="test-output-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )

    glue = boto3.client("glue", region_name="eu-west-2")
    glue.create_database(DatabaseInput={"Name": "test_db"})

    os.environ["DATABASE_PW_SECRET_ARN"] = _create_secret("super-secret")

    original_connect = module_under_test.pymssql.connect
    original_read_sql_query = module_under_test.pd.read_sql_query

    def fake_connect(**kwargs):
        return object()

    def fake_read_sql_query(query, conn):
        return pd.DataFrame(
            [
                {"view_name": "vw_example_1", "view_definition": "SELECT 1"},
                {"view_name": "vw_example_2", "view_definition": "SELECT 2"},
            ]
        )

    module_under_test.pymssql.connect = fake_connect
    module_under_test.pd.read_sql_query = fake_read_sql_query

    try:
        result = module_under_test.handler(event, context=None)
    finally:
        module_under_test.pymssql.connect = original_connect
        module_under_test.pd.read_sql_query = original_read_sql_query

    assert result == {
        "export_view_status": "2 definitions extracted to s3://test-output-bucket/test_db/view_definitions/"
    }

    objects = s3.list_objects_v2(Bucket="test-output-bucket").get("Contents", [])
    assert any(obj["Key"].startswith("test_db/view_definitions/") for obj in objects)


def test_handler_raises_when_secret_missing(event, module_under_test):
    """Raises when database password secret cannot be retrieved."""

    os.environ["DATABASE_PW_SECRET_ARN"] = (
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:missing"
    )

    with pytest.raises(Exception):
        module_under_test.handler(event, context=None)


def test_handler_raises_when_database_connection_fails(event, module_under_test):
    """Raises when SQL Server connection fails."""

    os.environ["DATABASE_PW_SECRET_ARN"] = _create_secret("super-secret")

    original_connect = module_under_test.pymssql.connect

    def fake_connect(**kwargs):
        raise RuntimeError("cannot connect")

    module_under_test.pymssql.connect = fake_connect

    try:
        with pytest.raises(RuntimeError, match="cannot connect"):
            module_under_test.handler(event, context=None)
    finally:
        module_under_test.pymssql.connect = original_connect
