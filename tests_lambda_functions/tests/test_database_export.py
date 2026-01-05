import pytest
import pandas as pd
import sys
import types

fake_pymssql = types.SimpleNamespace(connect=lambda *a, **k: None)
sys.modules["pymssql"] = fake_pymssql

from lambda_functions.database_export.main import (  # noqa: E402
    safe_decode,
    get_rowversion_cols,
    get_secret_value,
    decode_columns,
)


@pytest.fixture
def base_event():
    return {
        "db_endpoint": "mydb.abcdefg.eu-west-2.rds.amazonaws.com",
        "db_username": "admin",
        "output_bucket": "out-bucket",
        "extraction_timestamp": "2026-01-02T10:11:12",
        "chunk": {
            "database": "testdb",
            "table": "my_table",
            "query": "SELECT * FROM my_table",
        },
    }


@pytest.fixture
def sample_df_bytes():
    return pd.DataFrame(
        {
            "rv": [b"\x01\x02", b"\x10\xff"],
            "name": [b"alice", b"bob"],
            "age": [1, 2],
            "nullable": [None, b"x"],
        }
    )


def test_safe_decode():
    assert safe_decode("hello") == "hello"
    assert safe_decode(123) == 123
    assert safe_decode(None) is None


def test_safe_decode_cp1252_success():
    assert safe_decode(b"\x80") == "€"


# def test_decode_error:


def test_get_rowversion_cols(mocker):
    conn = mocker.Mock()

    cur = mocker.MagicMock()
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = None

    conn.cursor.return_value = cur
    cur.fetchall.return_value = [("rv", "test1"), ("ts", "test2")]

    cols = get_rowversion_cols(conn, table="my_table", schema="dbo")

    assert cols == {"rv", "ts"}
    assert cur.execute.call_count == 1

    sql, params = cur.execute.call_args.args
    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert params == ("dbo", "my_table")


def get_secret_value_success(mocker):
    mocker.patch(
        "lambda_functions.database_export.main.secretmanager.get_secret_value",
        return_value={"SecretString": "pw"},
    )

    assert (
        get_secret_value("arn:aws:secretsmanager:eu-west-2:123456789012:secret:test")
        == "pw"
    )


def test_get_secret_value_failure(mocker):
    mocker.patch(
        "lambda_functions.database_export.main.secretmanager.get_secret_value",
        side_effect=RuntimeError("boom"),
    )

    with pytest.raises(Exception, match="boom"):
        get_secret_value("arn:aws:secretsmanager:eu-west-2:123456789012:secret:test")


def test_decode_columns_rowversion_is_hex(sample_df_bytes):
    df = sample_df_bytes.copy()
    out = decode_columns(df, rowversion_cols={"rv"})

    assert out["rv"].tolist() == ["0102", "10ff"]
    assert out["name"].tolist() == ["alice", "bob"]


def test_decode_columns_only_decodes_bytes_columns(sample_df_bytes, mocker):
    df = sample_df_bytes.copy()

    out = decode_columns(df, rowversion_cols=set())

    assert out["name"].tolist() == ["alice", "bob"]
    assert out["age"].tolist() == [1, 2]


def test_decode_columns_empty_or_non_bytes_column_untouched(mocker):
    df = pd.DataFrame({"a": [None, None], "b": ["x", "y"]})
    out = decode_columns(df.copy(), rowversion_cols=set())
    assert out.equals(df)
