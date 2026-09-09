import pytest

from sqlmini.errors import ExecutionError
from sqlmini.table import Table, infer_column_type


def test_infers_int_column():
    assert infer_column_type(["1", "2", "3"]) == "int"


def test_infers_float_column_when_any_value_has_decimal():
    assert infer_column_type(["1", "2.5", "3"]) == "float"


def test_infers_bool_column():
    assert infer_column_type(["true", "false", "TRUE"]) == "bool"


def test_falls_back_to_str_for_mixed_content():
    assert infer_column_type(["1", "abc", "3"]) == "str"


def test_empty_values_ignored_for_inference():
    assert infer_column_type(["1", "", "3"]) == "int"


def test_all_empty_column_defaults_to_str():
    assert infer_column_type(["", ""]) == "str"


def test_from_csv_text_coerces_types_and_nulls():
    table = Table.from_csv_text(
        "t", "id,name,score,active\n1,Alice,9.5,true\n2,Bob,,false\n3,,7,\n"
    )
    assert table.columns == ["id", "name", "score", "active"]
    assert table.column_types == {"id": "int", "name": "str", "score": "float", "active": "bool"}
    assert table.rows[0] == {"id": 1, "name": "Alice", "score": 9.5, "active": True}
    assert table.rows[1] == {"id": 2, "name": "Bob", "score": None, "active": False}
    assert table.rows[2] == {"id": 3, "name": None, "score": 7.0, "active": None}


def test_from_csv_text_empty_file():
    table = Table.from_csv_text("t", "")
    assert table.columns == []
    assert table.rows == []


def test_from_csv_text_header_only():
    table = Table.from_csv_text("t", "a,b,c\n")
    assert table.columns == ["a", "b", "c"]
    assert table.rows == []


def test_ragged_row_raises_execution_error():
    with pytest.raises(ExecutionError):
        Table.from_csv_text("t", "a,b\n1,2,3\n")


def test_from_csv_path(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("a,b\n1,x\n2,y\n")
    table = Table.from_csv_path("t", str(p))
    assert len(table) == 2
    assert table.rows[0] == {"a": 1, "b": "x"}
