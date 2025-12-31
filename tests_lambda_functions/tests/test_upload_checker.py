from lambda_functions.upload_checker.main import handler
import pytest
import json


def test_raises_value_error(monkeypatch):
    monkeypatch.setenv(
        "STATE_MACHINE_ARN", "arn:aws:states:eu-west-2:123456789012:stateMachine:test"
    )
    monkeypatch.setenv("DB_NAME", "test_db_name")
    monkeypatch.setenv("OUTPUT_BUCKET", "test-output-bucket")
    monkeypatch.setenv("NAME", "test-name")
    monkeypatch.setenv("ENVIRONMENT", "test")

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "test"}, "object": {"key": "test_object.csv"}}}
        ]
    }

    with pytest.raises(ValueError, match="Invalid file format. Expected a .bak file."):
        handler(event, context="")


def test_raises_exception(monkeypatch):
    monkeypatch.delenv("STATE_MACHINE_ARN", raising=False)

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "test"}, "object": {"key": "test_object.csv"}}}
        ]
    }

    with pytest.raises(Exception):
        handler(event, context="")


def test_successful_run(monkeypatch, mocker):
    monkeypatch.setenv(
        "STATE_MACHINE_ARN", "arn:aws:states:eu-west-2:123456789012:stateMachine:test"
    )
    monkeypatch.setenv("DB_NAME", "test_db_name")
    monkeypatch.setenv("OUTPUT_BUCKET", "test-output-bucket")
    monkeypatch.setenv("NAME", "test-name")
    monkeypatch.setenv("ENVIRONMENT", "test")

    mock_sf = mocker.Mock()
    mock_sf.start_execution.return_value = {
        "executionArn": "arn:aws:states:execution:test"
    }

    mocker.patch(
        "lambda_functions.upload_checker.main.boto3.client", return_value=mock_sf
    )

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "test"}, "object": {"key": "test_object.bak"}}}
        ]
    }

    handler(event, context="")

    mock_sf.start_execution.assert_called_once()
    kwargs = mock_sf.start_execution.call_args.kwargs

    assert (
        kwargs["stateMachineArn"]
        == "arn:aws:states:eu-west-2:123456789012:stateMachine:test"
    )

    payload = json.loads(kwargs["input"])
    assert payload["bak_upload_bucket"] == "test"
    assert payload["bak_upload_key"] == "test_object.bak"
    assert payload["db_name"] == "test_db_name"
    assert payload["output_bucket"] == "test-output-bucket"
    assert payload["name"] == "test-name"
    assert payload["environment"] == "test"
