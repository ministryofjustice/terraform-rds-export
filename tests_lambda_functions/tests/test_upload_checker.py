from lambda_functions.upload_checker.main import handler
import pytest
import json
import boto3
import os


@pytest.fixture
def restore_env():
    os.environ["STATE_MACHINE_ARN"] = (
        "arn:aws:states:eu-west-2:123456789012:stateMachine:test"
    )
    os.environ["DB_NAME"] = "test_db_name"
    os.environ["OUTPUT_BUCKET"] = "test-output-bucket"
    os.environ["NAME"] = "test-name"
    os.environ["ENVIRONMENT"] = "test"


def test_raises_value_error(restore_env):
    """Raises when uploaded file is not a .bak backup file."""

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "test"}, "object": {"key": "test_object.csv"}}}
        ]
    }

    with pytest.raises(ValueError, match="Invalid file format. Expected a .bak file."):
        handler(event, context=None)


def test_raises_exception(restore_env):
    """Raises when required environment variables are missing."""

    os.environ.pop("STATE_MACHINE_ARN", None)

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "test"}, "object": {"key": "test_object.bak"}}}
        ]
    }

    with pytest.raises(KeyError):
        handler(event, context=None)


def test_successful_run(restore_env):
    """Starts Step Functions execution with expected payload fields."""

    stepfunctions = boto3.client("stepfunctions", region_name="eu-west-2")

    state_machine = stepfunctions.create_state_machine(
        name="test-upload-checker-state-machine",
        definition=json.dumps(
            {
                "StartAt": "PassState",
                "States": {"PassState": {"Type": "Pass", "End": True}},
            }
        ),
        roleArn="arn:aws:iam::123456789012:role/DummyRole",
    )

    state_machine_arn = state_machine["stateMachineArn"]
    os.environ["STATE_MACHINE_ARN"] = state_machine_arn

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "test"}, "object": {"key": "test_object.bak"}}}
        ]
    }

    handler(event, context=None)

    executions = stepfunctions.list_executions(stateMachineArn=state_machine_arn)
    assert len(executions["executions"]) == 1

    execution = stepfunctions.describe_execution(
        executionArn=executions["executions"][0]["executionArn"]
    )
    payload = json.loads(execution["input"])
    assert payload["bak_upload_bucket"] == "test"
    assert payload["bak_upload_key"] == "test_object.bak"
    assert payload["db_name"] == "test_db_name"
    assert payload["output_bucket"] == "test-output-bucket"
    assert payload["name"] == "test-name"
    assert payload["environment"] == "test"
