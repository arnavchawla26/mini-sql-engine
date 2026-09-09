from sqlmini.errors import PlanError


def test_select_star_returns_all_columns_and_rows(small_engine):
    result = small_engine.run("SELECT * FROM employees")
    assert result.columns == ["id", "name", "department_id", "salary", "is_manager"]
    assert len(result.rows) == 5


def test_select_specific_columns_with_alias(small_engine):
    result = small_engine.run("SELECT name AS employee, salary FROM employees")
    assert result.columns == ["employee", "salary"]
    assert ("Alice", 90000) in result.rows


def test_where_numeric_comparison(small_engine):
    result = small_engine.run("SELECT name FROM employees WHERE salary > 70000")
    names = {r[0] for r in result.rows}
    assert names == {"Alice", "Bob", "Cara"}


def test_where_and_or_precedence(small_engine):
    # is_manager = true OR (department_id = 20 AND salary < 65000)  -> Alice, Cara (managers) + Dan
    result = small_engine.run(
        "SELECT name FROM employees WHERE is_manager = TRUE OR department_id = 20 AND salary < 65000"
    )
    names = {r[0] for r in result.rows}
    assert names == {"Alice", "Cara", "Dan"}


def test_where_not(small_engine):
    result = small_engine.run("SELECT name FROM employees WHERE NOT is_manager = TRUE")
    names = {r[0] for r in result.rows}
    assert names == {"Bob", "Dan", "Eve"}


def test_where_string_equality(small_engine):
    result = small_engine.run("SELECT id FROM employees WHERE name = 'Alice'")
    assert result.rows == [(1,)]


def test_is_null_and_is_not_null(small_engine):
    result = small_engine.run("SELECT name FROM employees WHERE department_id IS NULL")
    assert result.rows == [("Eve",)]

    result = small_engine.run("SELECT COUNT(*) AS n FROM employees WHERE department_id IS NOT NULL")
    assert result.rows == [(4,)]


def test_order_by_asc_and_desc(small_engine):
    result = small_engine.run("SELECT name FROM employees ORDER BY salary DESC")
    assert [r[0] for r in result.rows] == ["Alice", "Bob", "Cara", "Dan", "Eve"]

    result = small_engine.run("SELECT name FROM employees ORDER BY salary ASC")
    assert [r[0] for r in result.rows] == ["Eve", "Dan", "Cara", "Bob", "Alice"]


def test_order_by_puts_nulls_last_in_both_directions(small_engine):
    asc = small_engine.run("SELECT name FROM employees ORDER BY department_id ASC, salary ASC")
    assert [r[0] for r in asc.rows][-1] == "Eve"

    desc = small_engine.run("SELECT name FROM employees ORDER BY department_id DESC")
    assert [r[0] for r in desc.rows][-1] == "Eve"


def test_order_by_multi_key(small_engine):
    result = small_engine.run("SELECT name FROM employees ORDER BY department_id ASC, salary DESC")
    assert [r[0] for r in result.rows] == ["Alice", "Bob", "Cara", "Dan", "Eve"]


def test_order_by_alias(small_engine):
    result = small_engine.run("SELECT salary AS s FROM employees ORDER BY s DESC LIMIT 1")
    assert result.rows == [(90000,)]


def test_limit(small_engine):
    result = small_engine.run("SELECT name FROM employees ORDER BY salary DESC LIMIT 2")
    assert [r[0] for r in result.rows] == ["Alice", "Bob"]


def test_distinct(small_engine):
    result = small_engine.run("SELECT DISTINCT is_manager FROM employees")
    assert {r[0] for r in result.rows} == {True, False}
    assert len(result.rows) == 2


def test_unknown_column_raises_plan_error(small_engine):
    try:
        small_engine.run("SELECT nope FROM employees")
        assert False, "expected PlanError"
    except PlanError:
        pass


def test_unknown_table_raises_plan_error(small_engine):
    try:
        small_engine.run("SELECT * FROM nowhere")
        assert False, "expected PlanError"
    except PlanError:
        pass
