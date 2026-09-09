"""Logical plan node definitions.

The planner turns a (resolved) `SelectStmt` into a tree of these nodes; the
executor walks the tree bottom-up. Every `ColumnRef` inside a plan node has
already been resolved to carry an explicit `table` (the source table's
alias), so the executor never has to guess which side of a join a bare
column name came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .ast_nodes import AggregateCall, ColumnRef, Condition, Expr


@dataclass
class PlanNode:
    """Base class; subclasses below are the concrete operators."""


@dataclass
class ScanNode(PlanNode):
    table: str  # name in the catalog
    alias: str


@dataclass
class JoinNode(PlanNode):
    left: PlanNode
    right: PlanNode
    left_key: ColumnRef
    right_key: ColumnRef
    kind: str = "INNER"  # INNER | LEFT


@dataclass
class FilterNode(PlanNode):
    child: PlanNode
    cond: Condition


@dataclass(frozen=True)
class AggRef:
    """A reference, inside a post-aggregation clause (SELECT/HAVING/ORDER BY),
    to one of the values an `AggregateNode` computed per group. `key` is the
    synthetic column the aggregate's value was stored under."""

    key: str
    call: AggregateCall


@dataclass
class AggregateSpec:
    """One aggregate expression appearing anywhere in SELECT/HAVING/ORDER BY,
    deduplicated by (func, resolved-arg, distinct) and given a synthetic key
    so every clause referring to the "same" aggregate shares one computed
    value."""

    key: str
    call: AggregateCall


@dataclass
class AggregateNode(PlanNode):
    child: PlanNode
    group_by: List[ColumnRef]
    aggregates: List[AggregateSpec]


@dataclass
class SortKey:
    expr: Expr  # ColumnRef or AggregateCall (post-resolution)
    descending: bool = False


@dataclass
class SortNode(PlanNode):
    child: PlanNode
    keys: List[SortKey]


@dataclass
class ProjectItem:
    expr: Expr  # ColumnRef, Literal, AggregateCall, or a Star marker handled separately
    output_name: str


@dataclass
class ProjectNode(PlanNode):
    child: PlanNode
    items: List[ProjectItem]


@dataclass
class DistinctNode(PlanNode):
    child: PlanNode


@dataclass
class LimitNode(PlanNode):
    child: PlanNode
    n: int


@dataclass
class Plan:
    """Top-level container returned by the planner."""

    root: PlanNode
    output_columns: List[str]
    # Maps an aggregate's synthetic key back to its call, shared by every
    # node in the tree that needs to compute or reference it.
    aggregate_specs: List[AggregateSpec] = field(default_factory=list)
