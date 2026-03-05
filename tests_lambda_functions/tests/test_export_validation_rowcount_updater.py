from lambda_functions.export_validation_rowcount_updater.main import (
    get_query_result,
    handler,
    run_athena_query,
)
import pytest
import boto3
import os


@pytest.fixture
def restore_env():
    os.environ["OUTPUT_BUCKET"] = "test-output-bucket"
    os.environ["DATABASE_REFRESH_MODE"] = "incremental"


@pytest.fixture
def event():
    return {
        "chunk": {
            "database": "test_db",
            "table": "my_table",
            "extraction_timestamp": "2026-02-26T12:00:00",
        }
    }


def _get_new_query_texts(athena, existing_ids):
    current_ids = athena.list_query_executions().get("QueryExecutionIds", [])
    new_ids = [query_id for query_id in current_ids if query_id not in existing_ids]
    return [
        athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]["Query"]
        for query_id in new_ids
    ]


def test_run_athena_query_success(restore_env):
    """Returns query id for a successful Athena execution."""

    athena = boto3.client("athena", region_name="eu-west-2")

    query_id = run_athena_query("SELECT 1", "test_db", "test-output-bucket")

    execution = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
    assert execution["Status"]["State"] == "SUCCEEDED"
    assert execution["QueryExecutionContext"]["Database"] == "test_db"
    assert execution["ResultConfiguration"]["OutputLocation"].startswith(
        "s3://test-output-bucket/athena-results/"
    )


def test_get_query_result_returns_zero_when_missing_data(restore_env):
    """Returns zero when Athena query result has no data rows."""

    query_id = run_athena_query("SELECT 1", "test_db", "test-output-bucket")

    # queries are not executed by Moto
    # get_query_result always returns 0 rows by default
    assert get_query_result(query_id) == "0"


def test_handler_full_refresh_success(restore_env, event):
    """Runs full-refresh flow and writes rowcount validation queries."""

    os.environ.pop("DATABASE_REFRESH_MODE", None)
    athena = boto3.client("athena", region_name="eu-west-2")
    existing_ids = athena.list_query_executions().get("QueryExecutionIds", [])

    result = handler(event, context=None)

    assert result["status"] == "success"
    assert result["table"] == "test_db.my_table"
    assert result["original_row_count"] == "NULL"
    assert result["exported_row_count"] == "0"

    queries = _get_new_query_texts(athena, existing_ids)
    assert any('FROM "test_db"."my_table"' in query for query in queries)
    assert not any(
        "WHERE extraction_timestamp = '2026-02-26T12:00:00'" in query
        and 'FROM "test_db"."my_table"' in query
        for query in queries
    )
    assert any(
        "DELETE FROM test_db.table_export_validation" in query for query in queries
    )
    assert any(
        'INSERT INTO "test_db"."table_export_validation"' in query for query in queries
    )


def test_handler_incremental_refresh_success(restore_env, event):
    """Runs incremental flow and includes extraction timestamp filter."""

    athena = boto3.client("athena", region_name="eu-west-2")
    existing_ids = athena.list_query_executions().get("QueryExecutionIds", [])
    extraction_timestamp_check = "2026-02-26T12:00:00"

    result = handler(event, context=None)

    assert result["status"] == "success"
    assert result["table"] == "test_db.my_table"

    queries = _get_new_query_texts(athena, existing_ids)
    assert any(
        'FROM "test_db"."my_table"' in query
        and f"WHERE extraction_timestamp = '{extraction_timestamp_check}'" in query
        for query in queries
    )


def test_raises_key_error_when_output_bucket_missing(restore_env, event):
    """Raises when required OUTPUT_BUCKET environment variable is missing."""

    os.environ.pop("OUTPUT_BUCKET", None)

    with pytest.raises(KeyError):
        handler(event, context=None)
