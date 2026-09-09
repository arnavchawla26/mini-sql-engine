def test_inner_join_matches_and_drops_unmatched(small_engine):
    # Eve has no department_id (NULL) and dept 30 has no employees, so an
    # inner join must drop Eve and never surface "Empty Dept".
    result = small_engine.run(
        "SELECT e.name, d.name AS dept "
        "FROM employees e JOIN departments d ON e.department_id = d.id "
        "ORDER BY e.name"
    )
    assert result.columns == ["name", "dept"]
    names = [r[0] for r in result.rows]
    assert names == ["Alice", "Bob", "Cara", "Dan"]
    assert ("Alice", "Engineering") in result.rows
    assert ("Cara", "Sales") in result.rows


def test_left_join_keeps_unmatched_left_rows_with_nulls(small_engine):
    result = small_engine.run(
        "SELECT e.name, d.name AS dept "
        "FROM employees e LEFT JOIN departments d ON e.department_id = d.id "
        "ORDER BY e.name"
    )
    rows = dict(result.rows)
    assert len(result.rows) == 5  # every employee kept, including Eve
    assert rows["Eve"] is None


def test_join_then_where_filters_joined_rows(small_engine):
    result = small_engine.run(
        "SELECT e.name "
        "FROM employees e JOIN departments d ON e.department_id = d.id "
        "WHERE d.name = 'Engineering'"
    )
    assert {r[0] for r in result.rows} == {"Alice", "Bob"}


def test_join_column_disambiguation_by_alias(small_engine):
    # both tables have an `id` and a `name` column; qualifying resolves the
    # ambiguity, an unqualified reference to either should raise.
    from sqlmini.errors import PlanError

    try:
        small_engine.run(
            "SELECT name FROM employees e JOIN departments d ON e.department_id = d.id"
        )
        assert False, "expected an ambiguous-column PlanError"
    except PlanError as exc:
        assert "ambiguous" in str(exc)


def test_self_join_style_alias_reuse_is_rejected(small_engine):
    from sqlmini.errors import PlanError

    try:
        small_engine.run(
            "SELECT * FROM employees e JOIN departments e ON e.department_id = e.id"
        )
        assert False, "expected a duplicate-alias PlanError"
    except PlanError:
        pass
