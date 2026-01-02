from lambda_functions.database_restore_status.main import handler
import pytest


@pytest.fixture
def base_event():
    return {
        "db_endpoint": "mydb.abcdefg.eu-west-2.rds.amazonaws.com",
        "db_username": "admin",
        "db_name": "testdb",
        "task_id": 123,
    }


def test_secretmanager_raises_error(base_event, mocker, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )

    mocker.patch(
        "lambda_functions.database_restore_status.main.secretmanager.get_secret_value",
        side_effect=RuntimeError,
    )

    result = handler(event=base_event, context=None)

    assert result is None


def test_handler_valid(base_event, mocker, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )
    mocker.patch(
        "lambda_functions.database_restore_status.main.secretmanager.get_secret_value",
        return_value={"SecretString": "pw"},
    )

    cursor = mocker.Mock()
    conn = mocker.Mock()
    conn.cursor.return_value = cursor
    connect = mocker.patch(
        "lambda_functions.database_restore_status.main.pytds.connect", return_value=conn
    )

    cursor.fetchone.return_value = (0, 1, 2, 3, 4, "SUCCESS")
    cursor.nextset.return_value = False  # shouldn't be used in this scenario

    assert handler(event=base_event, context=None) == {"restore_status": "SUCCESS"}

    connect.assert_called_once_with(
        server=base_event["db_endpoint"],
        database="master",
        user=base_event["db_username"],
        password="pw",
        timeout=5,
    )

    executed_sql = cursor.execute.call_args.args[0]
    assert "exec msdb.dbo.rds_task_status" in executed_sql
    assert "@db_name='testdb'" in executed_sql
    assert "@task_id='123'" in executed_sql

    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_handler_failure(base_event, mocker, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PW_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test",
    )
    mocker.patch(
        "lambda_functions.database_restore_status.main.secretmanager.get_secret_value",
        return_value={"SecretString": "pw"},
    )

    cursor = mocker.Mock()
    cursor.execute.side_effect = RuntimeError("bad sql")

    conn = mocker.Mock()
    conn.cursor.return_value = cursor

    mocker.patch(
        "lambda_functions.database_restore_status.main.pytds.connect", return_value=conn
    )

    with pytest.raises(RuntimeError, match="bad sql"):
        handler(event=base_event, context=None)

    cursor.close.assert_called_once()
    conn.close.assert_called_once()
