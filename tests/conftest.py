import os

import pytest

from sqlmini.engine import Engine
from sqlmini.table import Table

EXAMPLES_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "examples", "data")


@pytest.fixture
def small_engine() -> Engine:
    """A tiny two-table engine (employees / departments) built directly from
    in-memory CSV text, independent of the example fixtures, so unit tests
    don't break if examples/data changes."""
    engine = Engine()
    engine.register_table(
        Table.from_csv_text(
            "employees",
            "id,name,department_id,salary,is_manager\n"
            "1,Alice,10,90000,true\n"
            "2,Bob,10,80000,false\n"
            "3,Cara,20,75000,true\n"
            "4,Dan,20,60000,false\n"
            "5,Eve,,55000,false\n",
        )
    )
    engine.register_table(
        Table.from_csv_text(
            "departments",
            "id,name\n10,Engineering\n20,Sales\n30,Empty Dept\n",
        )
    )
    return engine


@pytest.fixture
def examples_engine() -> Engine:
    engine = Engine()
    engine.register_directory(EXAMPLES_DATA_DIR)
    return engine
