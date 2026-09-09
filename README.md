# mini-sql-engine

A small SQL engine, written from scratch, that runs `SELECT` queries over
in-memory tables loaded from CSV files. No parser generator, no database
dependency — just a hand-written tokenizer, recursive-descent parser,
logical planner, and a set of execution operators (scan / filter / hash-join
/ aggregate / sort / project).

```
$ sqlmini --data-dir examples/data run "
    SELECT d.name AS dept, COUNT(*) AS headcount, AVG(e.salary) AS avg_salary
    FROM employees e JOIN departments d ON e.department_id = d.id
    GROUP BY d.name
    ORDER BY avg_salary DESC
  "
dept        | headcount | avg_salary
------------+-----------+------------------
Engineering | 4         | 125125.0
Marketing   | 2         | 94000.0
Sales       | 3         | 92166.66666666667
Support     | 2         | 71000.0
(4 rows)
```

## Why

Most "toy SQL engine" projects stop at parsing `SELECT col FROM table WHERE
x = y`. This one goes a step further through the whole pipeline a real
query engine has — tokenizer, parser, a resolved logical plan (not just an
AST interpreter), and dedicated execution operators including a hash join
and grouped aggregation — while staying small enough to read end to end in
one sitting.

## Supported SQL

```sql
SELECT [DISTINCT] select_list
FROM table [[AS] alias]
[[INNER | LEFT [OUTER]] JOIN table [[AS] alias] ON col = col]...
[WHERE condition]
[GROUP BY col, ...]
[HAVING condition]
[ORDER BY col [ASC|DESC], ...]
[LIMIT n]
```

- **Select list**: `*`, `table.*`, columns, `[AS] alias`, and
  `COUNT/SUM/AVG/MIN/MAX([DISTINCT] col | *)`.
- **WHERE / HAVING**: `=`, `!=`/`<>`, `<`, `<=`, `>`, `>=`, `IS [NOT] NULL`,
  `AND`, `OR`, `NOT`, parentheses. Literals: numbers, `'strings'` (with `''`
  as an escaped quote), `TRUE`/`FALSE`, `NULL`.
- **JOIN**: any number of `INNER`/`LEFT` joins, equi-join only
  (`a.col = b.col`); executed as a hash join (`O(n + m)` per join instead of
  a nested-loop scan).
- **GROUP BY / HAVING**: any number of grouping columns; every non-aggregated
  column in the select list must be a grouping column (checked at plan
  time, not left to run and silently return nonsense).
- **ORDER BY**: multiple keys, mixed `ASC`/`DESC`, can reference a `SELECT`
  alias or an aggregate; `NULL` always sorts last regardless of direction.
- **LIMIT**, **DISTINCT**.
- `--` line comments.

Not supported (kept out deliberately, to keep the engine small and
readable): subqueries, `UNION`, `INSERT`/`UPDATE`/`DELETE`, `LIKE`/`IN`,
window functions, non-equi joins, and full three-valued NULL logic in
boolean expressions (a comparison against `NULL` is simply `false`, rather
than SQL's `UNKNOWN`).

## Architecture

```
SQL text
   │  sqlmini/lexer.py     — hand-written tokenizer
   ▼
tokens
   │  sqlmini/parser.py    — recursive-descent parser
   ▼
AST (sqlmini/ast_nodes.py) — SelectStmt, Comparison, JoinClause, ...
   │  sqlmini/planner.py   — name resolution + aggregate bookkeeping
   ▼
logical plan (sqlmini/plan.py) — Scan → Join → Filter → Aggregate → Sort → Project → Limit
   │  sqlmini/executor.py  — walks the plan tree, evaluates expressions
   ▼
QueryResult (columns + rows)
```

The planner is what makes this an engine rather than an AST-walking
interpreter: it resolves every bare column name to the exact table alias it
came from (raising on unknown/ambiguous references *before* running
anything), decides which side of each `JOIN ... ON` belongs to the
already-built plan versus the newly joined table, and deduplicates repeated
aggregate expressions (`SELECT COUNT(*) ... ORDER BY COUNT(*)` computes
`COUNT(*)` once per group, not twice).

`sqlmini/table.py` handles CSV loading: it infers a type per column (`int`
→ `float` → `bool` → `str`, trying each in order across every non-empty
cell) so that `WHERE salary > 100000` compares numbers, not strings.

## Tech stack

Python 3.9+, standard library only (`csv`, `argparse`, `dataclasses`) — no
runtime dependencies. `pytest` for tests, `pyflakes` for linting.

## Install & run

```bash
pip install -e ".[dev]"

# one-off query
sqlmini --data-dir examples/data run "SELECT name FROM employees WHERE salary > 100000"

# --format table (default) | csv | json
sqlmini --data-dir examples/data --format csv run "SELECT * FROM departments"

# list the tables loaded from a directory
sqlmini --data-dir examples/data tables

# interactive REPL (statements end in ';')
sqlmini --data-dir examples/data shell
```

Point `--data-dir` at any directory of `*.csv` files — each file becomes a
table named after its filename (`employees.csv` → table `employees`). The
first row is the header; column types are inferred from the data.

## Example data

`examples/data/` has two small hand-written CSVs — `employees.csv` (12 rows,
including one employee with no department, to exercise `LEFT JOIN` and
`IS NULL`) and `departments.csv` (4 rows) — used by the integration tests
and the examples above.

## Tests

```bash
pip install -e ".[dev]"
pytest            # 86 tests: lexer, parser, planner errors, table/CSV
                   # loading, select/where/order/limit/distinct, joins
                   # (inner + left, including ambiguous/duplicate-alias
                   # errors), aggregates + HAVING, CLI (all three output
                   # formats, error paths, and the shell REPL), and
                   # end-to-end scenarios against the example CSVs.
pyflakes sqlmini tests
```

## Current status

**v1, functional and tested.** The full pipeline (lex → parse → plan →
execute) works end to end: `SELECT`/`WHERE`/`JOIN` (inner + left, hash
join)/`GROUP BY`/`HAVING`/`ORDER BY`/`LIMIT`/`DISTINCT`, a table/csv/json CLI,
and an interactive shell. 86 tests passing, `pyflakes` clean.

Possible follow-ups if this project gets picked up again: `IN (...)` and
`LIKE` in `WHERE`, subqueries in `FROM`, a query plan `EXPLAIN` command that
prints the resolved plan tree, and a simple cost-based join-order chooser
for queries with 3+ joined tables (right now joins execute strictly
left-to-right in the order they're written).

## License

MIT — see [LICENSE](LICENSE).
