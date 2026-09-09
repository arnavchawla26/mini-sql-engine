"""AST node definitions produced by the parser and consumed by the planner.

Kept intentionally flat (plain dataclasses, no visitor framework) since the
grammar is small. `Expr` is the union of every expression node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass(frozen=True)
class ColumnRef:
    name: str
    table: Optional[str] = None  # set when written as `table.column`

    def __str__(self) -> str:
        return f"{self.table}.{self.name}" if self.table else self.name


@dataclass(frozen=True)
class Literal:
    value: object  # int | float | str | bool | None


@dataclass(frozen=True)
class Star:
    """`*` or `table.*` in a select list."""

    table: Optional[str] = None


@dataclass(frozen=True)
class AggregateCall:
    func: str  # COUNT | SUM | AVG | MIN | MAX
    arg: Optional["Expr"]  # None only for COUNT(*)
    distinct: bool = False


Expr = Union[ColumnRef, Literal, AggregateCall]


@dataclass(frozen=True)
class Comparison:
    left: Expr
    op: str  # =, !=, <>, <, <=, >, >=, IS, IS NOT
    right: Expr


@dataclass(frozen=True)
class Logical:
    op: str  # AND | OR
    left: "Condition"
    right: "Condition"


@dataclass(frozen=True)
class Not:
    operand: "Condition"


Condition = Union[Comparison, Logical, Not]


@dataclass(frozen=True)
class SelectItem:
    expr: Union[ColumnRef, Star, AggregateCall]
    alias: Optional[str] = None

    def output_name(self) -> str:
        if self.alias:
            return self.alias
        if isinstance(self.expr, ColumnRef):
            return self.expr.name
        if isinstance(self.expr, AggregateCall):
            arg = "*" if self.expr.arg is None else str(self.expr.arg)
            return f"{self.expr.func}({arg})"
        return "*"


@dataclass(frozen=True)
class TableRef:
    name: str
    alias: Optional[str] = None

    @property
    def output_alias(self) -> str:
        return self.alias or self.name


@dataclass(frozen=True)
class JoinClause:
    table: TableRef
    on: Comparison
    kind: str = "INNER"  # INNER | LEFT


@dataclass(frozen=True)
class OrderItem:
    expr: ColumnRef
    descending: bool = False


@dataclass(frozen=True)
class SelectStmt:
    select_items: List[SelectItem]
    from_table: TableRef
    joins: List[JoinClause] = field(default_factory=list)
    where: Optional[Condition] = None
    group_by: List[ColumnRef] = field(default_factory=list)
    having: Optional[Condition] = None
    order_by: List[OrderItem] = field(default_factory=list)
    limit: Optional[int] = None
    distinct: bool = False
