from lambda_functions.database_restore.main import handler
import pytest


@pytest.fixture
def base_event():
    return {
        "DescribeDBResult": {
            "DbInstanceDetails": {
                "Endpoint": {"Address": "mydb.abcdefg.eu-west-2.rds.amazonaws.com"},
                "MasterUsername": "admin",
            }
        },
        "bak_upload_bucket": "my-bucket",
        "bak_upload_key": "path/to/file.bak",
        "db_name": "testdb",
    }


def test_missing_required_params(base_event, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )
    bad_event = base_event.copy()
    bad_event.pop("bak_upload_bucket")

    with pytest.raises(
        ValueError, match="Required parameters are missing in the event."
    ):
        handler(event=bad_event, context=None)


def test_secretmanager_raises_error(base_event, mocker, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )
    mocker.patch(
        "lambda_functions.database_restore.main.secretmanager.get_secret_value",
        side_effect=RuntimeError,
    )

    with pytest.raises(
        Exception, match="Error fetching database credentials from Secrets Manager."
    ):
        handler(event=base_event, context=None)


def test_handler_valid(base_event, mocker, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )

    mocker.patch(
        "lambda_functions.database_restore.main.secretmanager.get_secret_value",
        return_value={"SecretString": "pw"},
    )

    cursor = mocker.Mock()
    conn = mocker.Mock()
    conn.cursor.return_value = cursor

    mocker.patch(
        "lambda_functions.database_restore.main.pytds.connect", return_value=conn
    )

    cursor.fetchone.return_value = (456,)
    cursor.nextset.return_value = False

    result = handler(event=base_event, context=None)

    assert result["task_id"] == 456
    assert result["db_name"] == "testdb"
    assert result["db_identifier"] == "mydb"

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("DROP DATABASE [testdb]" in sql for sql in executed)
    assert any("rds_restore_database" in sql for sql in executed)
    assert any("arn:aws:s3:::my-bucket/path/to/file.bak" in sql for sql in executed)

    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_handler_failure(base_event, mocker, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )

    mocker.patch(
        "lambda_functions.database_restore.main.secretmanager.get_secret_value",
        return_value={"SecretString": "pw"},
    )

    mocker.patch(
        "lambda_functions.database_restore.main.pytds.connect",
        side_effect=RuntimeError("cannot connect"),
    )

    result = handler(base_event, None)

    assert result["status"] == "FAILED"
    assert "cannot connect" in result["error"]
