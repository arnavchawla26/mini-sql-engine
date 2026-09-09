"""Command-line interface: `sqlmini run "<SQL>" --data-dir DIR` and
`sqlmini shell --data-dir DIR` (a tiny REPL)."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import List, Optional

from .engine import Engine, QueryResult
from .errors import SqlMiniError


def format_table(result: QueryResult) -> str:
    if not result.columns:
        return "(no columns)"

    def cell(v) -> str:
        return "" if v is None else str(v)

    widths = [len(c) for c in result.columns]
    str_rows = [[cell(v) for v in row] for row in result.rows]
    for row in str_rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(v))

    def fmt_row(values: List[str]) -> str:
        return " | ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    lines = [fmt_row(result.columns)]
    lines.append("-+-".join("-" * w for w in widths))
    for row in str_rows:
        lines.append(fmt_row(row))
    lines.append(f"({len(result.rows)} row{'s' if len(result.rows) != 1 else ''})")
    return "\n".join(lines)


def format_csv(result: QueryResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().rstrip("\n")


def format_json(result: QueryResult) -> str:
    return json.dumps(result.as_dicts(), indent=2, default=str)


FORMATTERS = {"table": format_table, "csv": format_csv, "json": format_json}


def _run_one(engine: Engine, sql: str, fmt: str, out) -> int:
    try:
        result = engine.run(sql)
    except SqlMiniError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(FORMATTERS[fmt](result), file=out)
    return 0


def _shell(engine: Engine, fmt: str, out, in_stream) -> int:
    print(f"sqlmini shell — tables: {', '.join(engine.table_names()) or '(none)'}", file=out)
    print("Enter a SQL statement ending in ';', or 'exit' / 'quit'.", file=out)
    buffer = ""
    while True:
        prompt = "sqlmini> " if not buffer else "     ... "
        print(prompt, end="", file=out, flush=True)
        line = in_stream.readline()
        if line == "":
            print(file=out)
            return 0
        stripped = line.strip()
        if not buffer and stripped.lower() in ("exit", "quit", "exit;", "quit;"):
            return 0
        if not stripped and not buffer:
            continue
        buffer += (" " if buffer else "") + line.rstrip("\n")
        if stripped.endswith(";"):
            sql = buffer.strip()
            buffer = ""
            if not sql:
                continue
            _run_one(engine, sql, fmt, out)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sqlmini", description="A small SQL engine over in-memory CSV tables.")
    parser.add_argument("--data-dir", required=True, help="Directory of *.csv files to load as tables.")
    parser.add_argument("--format", choices=sorted(FORMATTERS), default="table", help="Output format.")

    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a single SQL statement.")
    run_p.add_argument("sql", help="The SELECT statement to run.")

    sub.add_parser("shell", help="Start an interactive REPL.")
    sub.add_parser("tables", help="List the tables loaded from --data-dir.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    engine = Engine()
    try:
        engine.register_directory(args.data_dir)
    except OSError as exc:
        print(f"error: could not read --data-dir {args.data_dir!r}: {exc}", file=sys.stderr)
        return 1

    if args.command == "run":
        return _run_one(engine, args.sql, args.format, sys.stdout)
    if args.command == "shell":
        return _shell(engine, args.format, sys.stdout, sys.stdin)
    if args.command == "tables":
        for name in engine.table_names():
            t = engine.table(name)
            print(f"{name} ({len(t)} rows, columns: {', '.join(t.columns)})")
        return 0

    raise AssertionError("unreachable")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
