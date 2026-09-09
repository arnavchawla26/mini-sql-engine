"""Top-level `Engine`: register CSV tables, run SQL, get back a `QueryResult`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

from .executor import run_plan
from .parser import parse
from .planner import build_plan
from .table import Table


@dataclass
class QueryResult:
    columns: List[str]
    rows: List[tuple]

    def __len__(self) -> int:
        return len(self.rows)

    def as_dicts(self) -> List[Dict[str, object]]:
        return [dict(zip(self.columns, row)) for row in self.rows]


class Engine:
    """A tiny in-memory database: a named collection of CSV-backed tables
    plus a `run()` method that parses, plans, and executes a SELECT."""

    def __init__(self) -> None:
        self._catalog: Dict[str, Table] = {}

    def register_csv(self, name: str, path: str) -> Table:
        table = Table.from_csv_path(name, path)
        self._catalog[name] = table
        return table

    def register_table(self, table: Table) -> None:
        self._catalog[table.name] = table

    def register_directory(self, directory: str) -> List[str]:
        """Load every `*.csv` file in `directory` as a table named after its
        filename (without extension). Returns the names registered."""
        names = []
        for fname in sorted(os.listdir(directory)):
            if fname.endswith(".csv"):
                name = fname[: -len(".csv")]
                self.register_csv(name, os.path.join(directory, fname))
                names.append(name)
        return names

    def table_names(self) -> List[str]:
        return sorted(self._catalog)

    def table(self, name: str) -> Table:
        return self._catalog[name]

    def run(self, sql: str) -> QueryResult:
        stmt = parse(sql)
        plan = build_plan(stmt, self._catalog)
        rows = run_plan(plan, self._catalog)
        tuples = [tuple(r.get(col) for col in plan.output_columns) for r in rows]
        return QueryResult(columns=plan.output_columns, rows=tuples)
