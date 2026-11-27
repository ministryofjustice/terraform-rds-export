import importlib
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def database_export():
    module_name = "lambda_functions.database_export.main"
    external_dependencies = {
        name: MagicMock()
        for name in ("boto3", "pymssql", "awswrangler")
    }

    with patch.dict(sys.modules, external_dependencies):
        module = importlib.import_module(module_name)
        sys.modules.pop(module_name)

    return module


def test_safe_decode_decodes_cp1252_bytes(database_export):
    assert database_export.safe_decode("é".encode("cp1252")) == "é"

def test_safe_decode_falls_back_to_utf8(database_export):
    assert database_export.safe_decode("Ł".encode("utf-8")) == "Ł"

def test_safe_decode_falls_back_to_latin1(database_export):
    assert database_export.safe_decode(b"\x81") == "\x81"


def test_decode_columns_decodes_bytes_and_rowversions(database_export):
    data = pd.DataFrame({"name": [b"hello"], "version": [b"\x01\xff"]})

    result = database_export.decode_columns(data, {"version"})

    assert result["name"].tolist() == ["hello"]
    assert result["version"].tolist() == ["01ff"]


def test_handler_requires_db_endpoint(database_export):
    with pytest.raises(KeyError, match="db_endpoint"):
        database_export.handler({}, None)
