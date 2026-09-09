"""Planner: turns a parsed `SelectStmt` into a resolved `Plan`.

Two responsibilities live here that the parser deliberately leaves alone:

1. Name resolution — every bare column name gets tied to the exact table
   alias it came from (or rejected as unknown/ambiguous), and JOIN ... ON
   sides get sorted into (existing-scope side, new-table side).
2. Aggregate bookkeeping — every distinct aggregate expression appearing in
   SELECT / HAVING / ORDER BY is registered once and given a synthetic key,
   so the executor computes it once per group and every clause referring to
   "the same" aggregate reads the same value.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .ast_nodes import (
    AggregateCall,
    ColumnRef,
    Comparison,
    Condition,
    Expr,
    JoinClause,
    Literal,
    Logical,
    Not,
    SelectStmt,
    Star,
    TableRef,
)
from .errors import PlanError
from .plan import (
    AggRef,
    AggregateNode,
    AggregateSpec,
    DistinctNode,
    FilterNode,
    JoinNode,
    LimitNode,
    Plan,
    PlanNode,
    ProjectItem,
    ProjectNode,
    ScanNode,
    SortKey,
    SortNode,
)
from .table import Table

Scope = List[Tuple[str, str]]  # (alias, table_name), in FROM/JOIN order


class AggregateRegistry:
    """Assigns a stable synthetic key to each distinct aggregate expression."""

    def __init__(self) -> None:
        self._keys: Dict[AggregateCall, str] = {}
        self._order: List[AggregateCall] = []

    def get_or_add(self, call: AggregateCall) -> str:
        if call not in self._keys:
            key = f"__agg{len(self._order)}__"
            self._keys[call] = key
            self._order.append(call)
        return self._keys[call]

    def specs(self) -> List[AggregateSpec]:
        return [AggregateSpec(key=self._keys[c], call=c) for c in self._order]


def _validate_table(name: str, catalog: Dict[str, Table]) -> None:
    if name not in catalog:
        available = ", ".join(sorted(catalog)) or "(none registered)"
        raise PlanError(f"unknown table {name!r}; available tables: {available}")


def resolve_column_ref(cr: ColumnRef, scope: Scope, catalog: Dict[str, Table]) -> ColumnRef:
    if cr.table:
        matches = [(a, t) for a, t in scope if a == cr.table]
        if not matches:
            raise PlanError(f"unknown table/alias {cr.table!r}")
        alias, tname = matches[0]
        if cr.name not in catalog[tname].columns:
            raise PlanError(f"table {alias!r} has no column {cr.name!r}")
        return ColumnRef(name=cr.name, table=alias)

    matches = [a for a, t in scope if cr.name in catalog[t].columns]
    if not matches:
        raise PlanError(f"unknown column {cr.name!r}")
    if len(matches) > 1:
        raise PlanError(f"ambiguous column {cr.name!r} (present in tables: {', '.join(matches)})")
    return ColumnRef(name=cr.name, table=matches[0])


def _resolve_scalar_or_agg(
    expr: Expr,
    scope: Scope,
    catalog: Dict[str, Table],
    allow_aggregate: bool,
    agg_registry: Optional[AggregateRegistry],
    group_set: Optional[set],
) -> Expr:
    if isinstance(expr, ColumnRef):
        rc = resolve_column_ref(expr, scope, catalog)
        if group_set is not None and (rc.table, rc.name) not in group_set:
            raise PlanError(
                f"column {rc} must appear in GROUP BY or be used inside an aggregate function"
            )
        return rc
    if isinstance(expr, Literal):
        return expr
    if isinstance(expr, AggregateCall):
        if not allow_aggregate or agg_registry is None:
            raise PlanError("aggregate functions are not allowed in WHERE or JOIN ... ON")
        resolved_arg = resolve_column_ref(expr.arg, scope, catalog) if expr.arg is not None else None
        call = AggregateCall(func=expr.func, arg=resolved_arg, distinct=expr.distinct)
        key = agg_registry.get_or_add(call)
        return AggRef(key=key, call=call)
    raise PlanError(f"unsupported expression: {expr!r}")


def _resolve_condition(
    cond: Condition,
    scope: Scope,
    catalog: Dict[str, Table],
    allow_aggregate: bool,
    agg_registry: Optional[AggregateRegistry] = None,
    group_set: Optional[set] = None,
) -> Condition:
    if isinstance(cond, Comparison):
        left = _resolve_scalar_or_agg(cond.left, scope, catalog, allow_aggregate, agg_registry, group_set)
        right = _resolve_scalar_or_agg(cond.right, scope, catalog, allow_aggregate, agg_registry, group_set)
        return Comparison(left=left, op=cond.op, right=right)
    if isinstance(cond, Logical):
        left = _resolve_condition(cond.left, scope, catalog, allow_aggregate, agg_registry, group_set)
        right = _resolve_condition(cond.right, scope, catalog, allow_aggregate, agg_registry, group_set)
        return Logical(op=cond.op, left=left, right=right)
    if isinstance(cond, Not):
        return Not(_resolve_condition(cond.operand, scope, catalog, allow_aggregate, agg_registry, group_set))
    raise PlanError(f"unsupported condition: {cond!r}")


def _build_source(
    from_table: TableRef, joins: List[JoinClause], catalog: Dict[str, Table]
) -> Tuple[PlanNode, Scope]:
    _validate_table(from_table.name, catalog)
    alias = from_table.output_alias
    scope: Scope = [(alias, from_table.name)]
    root: PlanNode = ScanNode(table=from_table.name, alias=alias)

    for j in joins:
        _validate_table(j.table.name, catalog)
        r_alias = j.table.output_alias
        if r_alias in {a for a, _ in scope}:
            raise PlanError(f"duplicate table alias {r_alias!r} in FROM/JOIN")

        if j.on.op != "=":
            raise PlanError("JOIN ... ON currently only supports '=' (equi-joins)")
        if not isinstance(j.on.left, ColumnRef) or not isinstance(j.on.right, ColumnRef):
            raise PlanError("JOIN ... ON must compare two columns")

        extended_scope = scope + [(r_alias, j.table.name)]
        rc_left = resolve_column_ref(j.on.left, extended_scope, catalog)
        rc_right = resolve_column_ref(j.on.right, extended_scope, catalog)

        existing_aliases = {a for a, _ in scope}
        if rc_left.table in existing_aliases and rc_right.table == r_alias:
            left_key, right_key = rc_left, rc_right
        elif rc_right.table in existing_aliases and rc_left.table == r_alias:
            left_key, right_key = rc_right, rc_left
        else:
            raise PlanError(
                f"JOIN ... ON for {r_alias!r} must relate it to a table already in scope"
            )

        right_node = ScanNode(table=j.table.name, alias=r_alias)
        root = JoinNode(left=root, right=right_node, left_key=left_key, right_key=right_key, kind=j.kind)
        scope = extended_scope

    return root, scope


def _expand_star(star: Star, scope: Scope, catalog: Dict[str, Table]) -> List[ProjectItem]:
    items = []
    for alias, tname in scope:
        if star.table is not None and star.table != alias:
            continue
        for col in catalog[tname].columns:
            items.append(ProjectItem(expr=ColumnRef(name=col, table=alias), output_name=col))
    if not items:
        raise PlanError(f"'{star.table}.*' matches no table in scope")
    return items


def build_plan(stmt: SelectStmt, catalog: Dict[str, Table]) -> Plan:
    root, scope = _build_source(stmt.from_table, stmt.joins, catalog)

    if stmt.where is not None:
        where_cond = _resolve_condition(stmt.where, scope, catalog, allow_aggregate=False)
        root = FilterNode(child=root, cond=where_cond)

    group_by_resolved = [resolve_column_ref(c, scope, catalog) for c in stmt.group_by]
    group_set = {(c.table, c.name) for c in group_by_resolved}

    select_has_agg = any(isinstance(item.expr, AggregateCall) for item in stmt.select_items)
    is_aggregate_query = bool(group_by_resolved) or select_has_agg or stmt.having is not None

    agg_registry = AggregateRegistry()

    if is_aggregate_query:
        if any(isinstance(item.expr, Star) for item in stmt.select_items):
            raise PlanError("SELECT * cannot be combined with GROUP BY / aggregate functions")

        resolved_items: List[ProjectItem] = []
        for item in stmt.select_items:
            resolved_expr = _resolve_scalar_or_agg(
                item.expr, scope, catalog, allow_aggregate=True, agg_registry=agg_registry, group_set=group_set
            )
            resolved_items.append(ProjectItem(expr=resolved_expr, output_name=item.output_name()))

        having_cond = None
        if stmt.having is not None:
            having_cond = _resolve_condition(
                stmt.having, scope, catalog, allow_aggregate=True, agg_registry=agg_registry, group_set=group_set
            )

        sort_keys: List[SortKey] = []
        for oi in stmt.order_by:
            matched = None
            if oi.expr.table is None:
                matched = next((it for it in resolved_items if it.output_name == oi.expr.name), None)
            if matched is not None:
                sort_keys.append(SortKey(expr=matched.expr, descending=oi.descending))
            else:
                rc = resolve_column_ref(oi.expr, scope, catalog)
                if (rc.table, rc.name) not in group_set:
                    raise PlanError(
                        f"ORDER BY column {rc} must be a GROUP BY column, a SELECT alias, "
                        "or an aggregate function"
                    )
                sort_keys.append(SortKey(expr=rc, descending=oi.descending))

        root = AggregateNode(child=root, group_by=group_by_resolved, aggregates=agg_registry.specs())
        if having_cond is not None:
            root = FilterNode(child=root, cond=having_cond)
        if sort_keys:
            root = SortNode(child=root, keys=sort_keys)
        root = ProjectNode(child=root, items=resolved_items)
        output_columns = [it.output_name for it in resolved_items]

    else:
        resolved_items = []
        for item in stmt.select_items:
            if isinstance(item.expr, Star):
                resolved_items.extend(_expand_star(item.expr, scope, catalog))
            elif isinstance(item.expr, ColumnRef):
                rc = resolve_column_ref(item.expr, scope, catalog)
                resolved_items.append(ProjectItem(expr=rc, output_name=item.output_name()))
            elif isinstance(item.expr, Literal):
                resolved_items.append(ProjectItem(expr=item.expr, output_name=item.output_name()))
            else:
                raise PlanError(f"unsupported select item: {item.expr!r}")

        sort_keys = []
        for oi in stmt.order_by:
            matched = None
            if oi.expr.table is None:
                matched = next(
                    (it for it in resolved_items if it.output_name == oi.expr.name and isinstance(it.expr, ColumnRef)),
                    None,
                )
            if matched is not None:
                sort_keys.append(SortKey(expr=matched.expr, descending=oi.descending))
            else:
                rc = resolve_column_ref(oi.expr, scope, catalog)
                sort_keys.append(SortKey(expr=rc, descending=oi.descending))
        if sort_keys:
            root = SortNode(child=root, keys=sort_keys)

        root = ProjectNode(child=root, items=resolved_items)
        output_columns = [it.output_name for it in resolved_items]

    if stmt.distinct:
        root = DistinctNode(child=root)

    if stmt.limit is not None:
        if stmt.limit < 0:
            raise PlanError("LIMIT must be non-negative")
        root = LimitNode(child=root, n=stmt.limit)

    return Plan(root=root, output_columns=output_columns, aggregate_specs=agg_registry.specs())
