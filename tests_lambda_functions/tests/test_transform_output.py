import pytest
import json
from lambda_functions.transform_output.main import handler, get_unique

test_data_get_unique_valid = [
    (
        [
            {"a": 1, "b": 2, "c": "string"},
            {"a": 1, "b": 2, "c": "string2"},
            {"a": 3, "b": 4, "c": "string2"},
        ],
        ["a", "b"],
        [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
    ),
    (
        [
            {"a": 1, "b": 2, "c": "string"},
            {"a": 1, "b": 2, "c": "string2"},
            {"a": 3, "b": 4, "c": "string2"},
        ],
        [],
        [{}],
    ),
    (
        [
            {"a": 1, "b": 2, "c": "string"},
            {"a": 1, "b": 2, "c": "string"},
            {"a": 3, "b": 4, "c": "string"},
        ],
        ["c"],
        [{"c": "string"}],
    ),
]

test_data_get_unique_key_error = [
    (
        [
            {"a": 1, "b": 2, "c": "string"},
            {"a": 1, "b": 2, "c": "string2"},
            {"a": 3, "b": 4, "c": "string2"},
        ],
        ["e"],
    ),
    (
        [
            {"a": 1, "b": 2, "c": "string"},
            {"a": 1, "b": 2, "c": "string"},
            {"a": 3, "b": 4},
        ],
        ["e", "c"],
    ),
]


@pytest.mark.parametrize("data,keys_to_keep,expected", test_data_get_unique_valid)
def test_get_unique(data, keys_to_keep, expected):
    assert {json.dumps(d, sort_keys=True) for d in get_unique(data, keys_to_keep)} == {
        json.dumps(d, sort_keys=True) for d in expected
    }


@pytest.mark.parametrize("data,keys_to_keep", test_data_get_unique_key_error)
def test_get_unique_key_error(data, keys_to_keep):
    with pytest.raises(KeyError, match="One or more required keys missing"):
        get_unique(data, keys_to_keep)


def test_handler_valid():
    event = {
        "chunks": [
            {"database": "db_1", "table": "tb_1", "a": 1},
            {"database": "db_1", "table": "tb_1", "a": 2},
            {"database": "db_1", "table": "tb_2", "b": 2},
        ],
        "input_a": "test",
        "input_b": [],
    }

    expected = [
        {"database": "db_1", "table": "tb_1"},
        {"database": "db_1", "table": "tb_2"},
    ]

    assert {
        json.dumps(d, sort_keys=True) for d in handler(event, context=None)["tables"]
    } == {json.dumps(d, sort_keys=True) for d in expected}


def test_handler_key_error():
    event = {
        "chunks": [
            {"a": "db_1", "b": "tb_1", "c": 1},
            {"database": "db_1", "table": "tb_1", "a": 2},
            {"c": "db_1", "table": "tb_2", "b": 2},
        ],
        "input_a": "test",
        "input_b": [],
    }

    with pytest.raises(KeyError, match="One or more required keys missing"):
        handler(event, context=None)
