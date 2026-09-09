import pytest

from sqlmini.errors import PlanError


def test_group_by_with_count_and_avg(small_engine):
    result = small_engine.run(
        "SELECT department_id, COUNT(*) AS n, AVG(salary) AS avg_sal "
        "FROM employees GROUP BY department_id ORDER BY department_id"
    )
    assert result.columns == ["department_id", "n", "avg_sal"]
    assert result.rows == [
        (10, 2, 85000.0),
        (20, 2, 67500.0),
        (None, 1, 55000.0),
    ]


def test_having_filters_groups(small_engine):
    result = small_engine.run(
        "SELECT department_id, COUNT(*) AS n "
        "FROM employees GROUP BY department_id HAVING COUNT(*) > 1 "
        "ORDER BY department_id"
    )
    assert result.rows == [(10, 2), (20, 2)]


def test_whole_table_aggregate_without_group_by(small_engine):
    result = small_engine.run(
        "SELECT COUNT(*) AS n, SUM(salary) AS total, AVG(salary) AS avg_sal, "
        "MIN(salary) AS lo, MAX(salary) AS hi FROM employees"
    )
    assert result.rows == [(5, 360000, 72000.0, 55000, 90000)]


def test_whole_table_aggregate_on_empty_result_still_returns_one_row(small_engine):
    result = small_engine.run("SELECT COUNT(*) AS n, SUM(salary) AS total FROM employees WHERE salary > 999999")
    assert result.rows == [(0, None)]


def test_count_distinct(small_engine):
    result = small_engine.run("SELECT COUNT(DISTINCT department_id) AS n FROM employees")
    assert result.rows == [(2,)]


def test_group_by_with_where_filters_before_aggregation(small_engine):
    result = small_engine.run(
        "SELECT department_id, COUNT(*) AS n FROM employees "
        "WHERE is_manager = FALSE GROUP BY department_id ORDER BY department_id"
    )
    assert result.rows == [(10, 1), (20, 1), (None, 1)]


def test_order_by_aggregate_alias(small_engine):
    result = small_engine.run(
        "SELECT department_id, COUNT(*) AS n FROM employees "
        "GROUP BY department_id ORDER BY n DESC, department_id ASC"
    )
    # dept 10 and 20 tie at n=2; department_id ASC breaks the tie; None-group (n=1) last.
    assert result.rows == [(10, 2), (20, 2), (None, 1)]


def test_non_grouped_column_without_aggregate_raises_plan_error(small_engine):
    with pytest.raises(PlanError):
        small_engine.run("SELECT department_id, name FROM employees GROUP BY department_id")


def test_select_star_with_group_by_raises_plan_error(small_engine):
    with pytest.raises(PlanError):
        small_engine.run("SELECT * FROM employees GROUP BY department_id")


def test_aggregate_in_where_raises_plan_error(small_engine):
    with pytest.raises(PlanError):
        small_engine.run("SELECT * FROM employees WHERE COUNT(*) > 1")
