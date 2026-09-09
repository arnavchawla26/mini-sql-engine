import pytest

from sqlmini.ast_nodes import (
    AggregateCall,
    ColumnRef,
    Comparison,
    JoinClause,
    Literal,
    Logical,
    Not,
    Star,
)
from sqlmini.errors import ParseError
from sqlmini.parser import parse


def test_parses_select_star():
    stmt = parse("SELECT * FROM employees")
    assert len(stmt.select_items) == 1
    assert isinstance(stmt.select_items[0].expr, Star)
    assert stmt.from_table.name == "employees"
    assert stmt.from_table.alias is None


def test_parses_column_list_with_aliases():
    stmt = parse("SELECT name AS n, salary sal FROM employees")
    a, b = stmt.select_items
    assert a.expr == ColumnRef(name="name")
    assert a.alias == "n"
    assert b.expr == ColumnRef(name="salary")
    assert b.alias == "sal"


def test_parses_table_alias():
    stmt = parse("SELECT e.name FROM employees AS e")
    assert stmt.from_table.alias == "e"
    assert stmt.select_items[0].expr == ColumnRef(name="name", table="e")


def test_parses_where_with_and_or_not_and_precedence():
    stmt = parse("SELECT * FROM t WHERE NOT a = 1 AND b = 2 OR c = 3")
    # AND binds tighter than OR: (NOT a=1 AND b=2) OR c=3
    assert isinstance(stmt.where, Logical)
    assert stmt.where.op == "OR"
    left = stmt.where.left
    assert isinstance(left, Logical)
    assert left.op == "AND"
    assert isinstance(left.left, Not)


def test_parses_parenthesized_condition():
    stmt = parse("SELECT * FROM t WHERE a = 1 AND (b = 2 OR c = 3)")
    assert isinstance(stmt.where, Logical)
    assert stmt.where.op == "AND"
    assert isinstance(stmt.where.right, Logical)
    assert stmt.where.right.op == "OR"


def test_parses_comparison_operators():
    for op in ["=", "!=", "<>", "<", "<=", ">", ">="]:
        stmt = parse(f"SELECT * FROM t WHERE a {op} 1")
        assert isinstance(stmt.where, Comparison)
        assert stmt.where.op == op


def test_parses_is_null_and_is_not_null():
    stmt = parse("SELECT * FROM t WHERE a IS NULL")
    assert stmt.where == Comparison(left=ColumnRef(name="a"), op="IS", right=Literal(None))

    stmt = parse("SELECT * FROM t WHERE a IS NOT NULL")
    assert stmt.where == Comparison(left=ColumnRef(name="a"), op="IS NOT", right=Literal(None))


def test_parses_string_number_bool_null_literals():
    stmt = parse("SELECT * FROM t WHERE a = 'x' AND b = 1 AND c = 1.5 AND d = TRUE AND e = FALSE")
    # just check it parses without error and produces nested AND logicals
    assert isinstance(stmt.where, Logical)


def test_parses_join_with_on():
    stmt = parse(
        "SELECT e.name, d.name FROM employees e JOIN departments d ON e.department_id = d.id"
    )
    assert len(stmt.joins) == 1
    join = stmt.joins[0]
    assert isinstance(join, JoinClause)
    assert join.kind == "INNER"
    assert join.table.name == "departments"
    assert join.table.alias == "d"
    assert join.on == Comparison(
        left=ColumnRef(name="department_id", table="e"),
        op="=",
        right=ColumnRef(name="id", table="d"),
    )


def test_parses_left_join():
    stmt = parse("SELECT * FROM a LEFT JOIN b ON a.id = b.a_id")
    assert stmt.joins[0].kind == "LEFT"


def test_parses_group_by_having_aggregate():
    stmt = parse(
        "SELECT department_id, COUNT(*) AS n, AVG(salary) "
        "FROM employees GROUP BY department_id HAVING COUNT(*) > 1"
    )
    assert stmt.group_by == [ColumnRef(name="department_id")]
    assert isinstance(stmt.having, Comparison)
    agg_items = [i.expr for i in stmt.select_items if isinstance(i.expr, AggregateCall)]
    assert agg_items[0] == AggregateCall(func="COUNT", arg=None)
    assert agg_items[1] == AggregateCall(func="AVG", arg=ColumnRef(name="salary"))


def test_count_star_requires_star_argument_for_count_only():
    with pytest.raises(ParseError):
        parse("SELECT SUM(*) FROM t")


def test_parses_order_by_multiple_with_directions():
    stmt = parse("SELECT * FROM t ORDER BY a ASC, b DESC, c")
    assert [(o.expr.name, o.descending) for o in stmt.order_by] == [
        ("a", False),
        ("b", True),
        ("c", False),
    ]


def test_parses_limit():
    stmt = parse("SELECT * FROM t LIMIT 5")
    assert stmt.limit == 5


def test_parses_distinct():
    stmt = parse("SELECT DISTINCT department_id FROM employees")
    assert stmt.distinct is True


def test_trailing_semicolon_allowed():
    stmt = parse("SELECT * FROM t;")
    assert stmt.from_table.name == "t"


def test_missing_from_raises_parse_error():
    with pytest.raises(ParseError):
        parse("SELECT *")


def test_trailing_garbage_raises_parse_error():
    with pytest.raises(ParseError):
        parse("SELECT * FROM t WHERE a = 1 potato")


def test_unclosed_paren_raises_parse_error():
    with pytest.raises(ParseError):
        parse("SELECT * FROM t WHERE (a = 1")
