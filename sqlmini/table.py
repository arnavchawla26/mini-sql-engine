"""In-memory table representation and CSV loading with type inference.

A `Table` is just a column list plus a list of row dicts. Loading a CSV
infers a type per column (int, float, bool, or str) by trying, in order,
int -> float -> bool -> str across every non-empty cell in that column;
if any cell fails a stricter type the whole column falls back to the next
looser one. Empty cells become `None` regardless of the column's type.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .errors import ExecutionError

_TRUE_STRINGS = {"true", "t", "yes", "y", "1"}
_FALSE_STRINGS = {"false", "f", "no", "n", "0"}


def _try_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except ValueError:
        return None


def _try_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except ValueError:
        return None


def _try_bool(s: str) -> Optional[bool]:
    low = s.strip().lower()
    if low in _TRUE_STRINGS:
        return True
    if low in _FALSE_STRINGS:
        return False
    return None


def infer_column_type(values: List[str]) -> str:
    """Return one of 'int', 'float', 'bool', 'str' for a column's raw cells."""
    non_empty = [v for v in values if v != ""]
    if not non_empty:
        return "str"

    if all(_try_int(v) is not None for v in non_empty):
        return "int"
    if all(_try_float(v) is not None for v in non_empty):
        return "float"
    if all(_try_bool(v) is not None for v in non_empty):
        return "bool"
    return "str"


def coerce(value: str, col_type: str):
    if value == "":
        return None
    if col_type == "int":
        return int(value)
    if col_type == "float":
        return float(value)
    if col_type == "bool":
        return _try_bool(value)
    return value


@dataclass
class Table:
    name: str
    columns: List[str]
    rows: List[Dict[str, object]] = field(default_factory=list)
    column_types: Dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.rows)

    @classmethod
    def from_csv_text(cls, name: str, text: str) -> "Table":
        reader = csv.reader(text.splitlines())
        rows_raw = list(reader)
        if not rows_raw:
            return cls(name=name, columns=[], rows=[], column_types={})

        header = [h.strip() for h in rows_raw[0]]
        data_rows = [r for r in rows_raw[1:] if r != []]

        column_types = {}
        for idx, col in enumerate(header):
            raw_values = [r[idx] if idx < len(r) else "" for r in data_rows]
            column_types[col] = infer_column_type(raw_values)

        rows: List[Dict[str, object]] = []
        for r in data_rows:
            if len(r) != len(header):
                raise ExecutionError(
                    f"table {name!r}: row {r!r} has {len(r)} fields, expected {len(header)}"
                )
            row = {col: coerce(r[idx], column_types[col]) for idx, col in enumerate(header)}
            rows.append(row)

        return cls(name=name, columns=header, rows=rows, column_types=column_types)

    @classmethod
    def from_csv_path(cls, name: str, path: str) -> "Table":
        with open(path, "r", newline="", encoding="utf-8") as fh:
            return cls.from_csv_text(name, fh.read())
