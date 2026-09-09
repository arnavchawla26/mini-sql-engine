"""Execution operators: walk a resolved `Plan` tree and produce rows.

Every intermediate row is a flat `dict`:
  - before aggregation, keys look like `"alias.column"`.
  - after aggregation, keys are `"alias.column"` for GROUP BY columns plus
    the synthetic `"__aggN__"` keys `AggregateNode` fills in.

`evaluate_expr` understands `ColumnRef` (pre- or post-aggregation, via its
`table`/`name`), `Literal`, and `AggRef` (post-aggregation only), so the same
function works for WHERE, HAVING, ORDER BY, and SELECT.
"""

from __future__ import annotations

import functools
from typing import Dict, List

from .ast_nodes import Comparison, Condition, Expr, Literal, Logical, Not, ColumnRef
from .errors import ExecutionError
from .plan import (
    AggRef,
    AggregateNode,
    DistinctNode,
    FilterNode,
    JoinNode,
    LimitNode,
    Plan,
    PlanNode,
    ProjectNode,
    ScanNode,
    SortNode,
)
from .table import Table

Row = Dict[str, object]


def _row_key(col: ColumnRef) -> str:
    return f"{col.table}.{col.name}"


def evaluate_expr(expr: Expr, row: Row):
    if isinstance(expr, ColumnRef):
        key = _row_key(expr)
        if key not in row:
            raise ExecutionError(f"internal error: column {key!r} missing from row")
        return row[key]
    if isinstance(expr, Literal):
        return expr.value
    if isinstance(expr, AggRef):
        return row[expr.key]
    raise ExecutionError(f"cannot evaluate expression: {expr!r}")


def _compare_values(left, op: str, right) -> bool:
    if op == "IS":
        return left is None
    if op == "IS NOT":
        return left is not None
    # Simplified NULL handling: any comparison against NULL (other than
    # IS [NOT] NULL) is false, rather than full three-valued SQL logic.
    if left is None or right is None:
        return False
    if op == "=":
        return left == right
    if op in ("!=", "<>"):
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise ExecutionError(f"unsupported comparison operator {op!r}")


def evaluate_condition(cond: Condition, row: Row) -> bool:
    if isinstance(cond, Comparison):
        return _compare_values(evaluate_expr(cond.left, row), cond.op, evaluate_expr(cond.right, row))
    if isinstance(cond, Logical):
        if cond.op == "AND":
            return evaluate_condition(cond.left, row) and evaluate_condition(cond.right, row)
        if cond.op == "OR":
            return evaluate_condition(cond.left, row) or evaluate_condition(cond.right, row)
        raise ExecutionError(f"unsupported logical operator {cond.op!r}")
    if isinstance(cond, Not):
        return not evaluate_condition(cond.operand, row)
    raise ExecutionError(f"cannot evaluate condition: {cond!r}")


def _compare_for_sort(a, b, descending: bool) -> int:
    """Comparator with NULLS LAST semantics regardless of direction: `None`
    always sorts after every real value. Plain `reverse=True` can't express
    this, since it flips the comparator sense for the null placement too."""
    if a is None and b is None:
        return 0
    if a is None:
        return 1
    if b is None:
        return -1
    if a == b:
        return 0
    less = a < b
    if descending:
        return -1 if not less else 1
    return -1 if less else 1


def _apply_sort(rows: List[Row], keys) -> List[Row]:
    result = list(rows)
    # Stable multi-key sort: apply from the least- to the most-significant
    # key, relying on sort() stability to build up the final ordering.
    for k in reversed(keys):
        result.sort(
            key=functools.cmp_to_key(
                lambda r1, r2: _compare_for_sort(evaluate_expr(k.expr, r1), evaluate_expr(k.expr, r2), k.descending)
            )
        )
    return result


def _aggregate_group(rows: List[Row], aggregates) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for spec in aggregates:
        call = spec.call
        if call.func == "COUNT" and call.arg is None:
            out[spec.key] = len(rows)
            continue

        values = [evaluate_expr(call.arg, r) for r in rows]
        values = [v for v in values if v is not None]
        if call.distinct:
            # dict.fromkeys preserves first-seen order; not that order
            # matters for these reductions, but it keeps output deterministic.
            values = list(dict.fromkeys(values))

        if call.func == "COUNT":
            out[spec.key] = len(values)
        elif call.func == "SUM":
            out[spec.key] = sum(values) if values else None
        elif call.func == "AVG":
            out[spec.key] = (sum(values) / len(values)) if values else None
        elif call.func == "MIN":
            out[spec.key] = min(values) if values else None
        elif call.func == "MAX":
            out[spec.key] = max(values) if values else None
        else:
            raise ExecutionError(f"unsupported aggregate function {call.func!r}")
    return out


def execute(node: PlanNode, catalog: Dict[str, Table]) -> List[Row]:
    if isinstance(node, ScanNode):
        table = catalog[node.table]
        return [
            {f"{node.alias}.{col}": row.get(col) for col in table.columns}
            for row in table.rows
        ]

    if isinstance(node, JoinNode):
        left_rows = execute(node.left, catalog)
        right_rows = execute(node.right, catalog)
        right_key = _row_key(node.right_key)
        left_key = _row_key(node.left_key)

        buckets: Dict[object, List[Row]] = {}
        for r in right_rows:
            buckets.setdefault(r[right_key], []).append(r)

        right_schema_keys = list(right_rows[0].keys()) if right_rows else _schema_keys(node.right, catalog)

        out: List[Row] = []
        for lrow in left_rows:
            matches = buckets.get(lrow[left_key], [])
            if matches:
                for rrow in matches:
                    merged = dict(lrow)
                    merged.update(rrow)
                    out.append(merged)
            elif node.kind == "LEFT":
                merged = dict(lrow)
                for k in right_schema_keys:
                    merged.setdefault(k, None)
                out.append(merged)
        return out

    if isinstance(node, FilterNode):
        rows = execute(node.child, catalog)
        return [r for r in rows if evaluate_condition(node.cond, r)]

    if isinstance(node, AggregateNode):
        rows = execute(node.child, catalog)
        group_keys = [_row_key(c) for c in node.group_by]

        if not group_keys:
            agg_values = _aggregate_group(rows, node.aggregates)
            return [agg_values]

        groups: Dict[tuple, List[Row]] = {}
        order: List[tuple] = []
        for r in rows:
            gkey = tuple(r[k] for k in group_keys)
            if gkey not in groups:
                groups[gkey] = []
                order.append(gkey)
            groups[gkey].append(r)

        out = []
        for gkey in order:
            group_rows = groups[gkey]
            row_out: Row = dict(zip(group_keys, gkey))
            row_out.update(_aggregate_group(group_rows, node.aggregates))
            out.append(row_out)
        return out

    if isinstance(node, SortNode):
        rows = execute(node.child, catalog)
        return _apply_sort(rows, node.keys)

    if isinstance(node, ProjectNode):
        rows = execute(node.child, catalog)
        return [{item.output_name: evaluate_expr(item.expr, r) for item in node.items} for r in rows]

    if isinstance(node, DistinctNode):
        rows = execute(node.child, catalog)
        seen = set()
        out = []
        for r in rows:
            key = tuple(sorted(r.items()))
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    if isinstance(node, LimitNode):
        rows = execute(node.child, catalog)
        return rows[: node.n]

    raise ExecutionError(f"unknown plan node: {node!r}")


def _schema_keys(node: PlanNode, catalog: Dict[str, Table]) -> List[str]:
    """Column keys a node's rows would carry, without materializing them.
    Only needed for the empty-right-side branch of a LEFT JOIN."""
    if isinstance(node, ScanNode):
        return [f"{node.alias}.{col}" for col in catalog[node.table].columns]
    if isinstance(node, JoinNode):
        return _schema_keys(node.left, catalog) + _schema_keys(node.right, catalog)
    if isinstance(node, (FilterNode, SortNode, DistinctNode, LimitNode)):
        return _schema_keys(node.child, catalog)
    if isinstance(node, ProjectNode):
        return [item.output_name for item in node.items]
    if isinstance(node, AggregateNode):
        return [_row_key(c) for c in node.group_by] + [s.key for s in node.aggregates]
    raise ExecutionError(f"cannot compute schema for node: {node!r}")


def run_plan(plan: Plan, catalog: Dict[str, Table]) -> List[Row]:
    return execute(plan.root, catalog)
