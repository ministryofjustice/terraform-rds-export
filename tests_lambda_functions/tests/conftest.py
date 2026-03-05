import os
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")

_MOTO_AWS = mock_aws()
_MOTO_AWS.start()


def pytest_sessionfinish(session, exitstatus):
    """Stop moto after the full pytest session completes."""
    _MOTO_AWS.stop()
