import io
import json
import os

from sqlmini.cli import main

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "examples", "data")


def run_cli(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_run_table_format(capsys):
    code, out, err = run_cli(["--data-dir", DATA_DIR, "run", "SELECT name FROM departments ORDER BY name"], capsys)
    assert code == 0
    assert err == ""
    assert "Engineering" in out
    assert "Marketing" in out
    assert "(4 rows)" in out


def test_run_csv_format(capsys):
    code, out, _ = run_cli(
        ["--data-dir", DATA_DIR, "--format", "csv", "run", "SELECT id, name FROM departments ORDER BY id"],
        capsys,
    )
    assert code == 0
    lines = out.strip().splitlines()
    assert lines[0] == "id,name"
    assert lines[1] == "1,Engineering"


def test_run_json_format(capsys):
    code, out, _ = run_cli(
        ["--data-dir", DATA_DIR, "--format", "json", "run", "SELECT id, name FROM departments WHERE id = 1"],
        capsys,
    )
    assert code == 0
    data = json.loads(out)
    assert data == [{"id": 1, "name": "Engineering"}]


def test_run_reports_parse_error_on_stderr(capsys):
    code, out, err = run_cli(["--data-dir", DATA_DIR, "run", "SELECT FROM"], capsys)
    assert code == 1
    assert out == ""
    assert "error:" in err


def test_run_reports_plan_error_on_stderr(capsys):
    code, out, err = run_cli(["--data-dir", DATA_DIR, "run", "SELECT nope FROM departments"], capsys)
    assert code == 1
    assert "error:" in err


def test_tables_subcommand_lists_loaded_tables(capsys):
    code, out, _ = run_cli(["--data-dir", DATA_DIR, "tables"], capsys)
    assert code == 0
    assert "departments (4 rows" in out
    assert "employees (12 rows" in out


def test_bad_data_dir_reports_error(capsys):
    code, out, err = run_cli(["--data-dir", "/no/such/directory", "tables"], capsys)
    assert code == 1
    assert "error:" in err


def test_shell_runs_query_and_exits(capsys, monkeypatch):
    from sqlmini.cli import _shell
    from sqlmini.engine import Engine

    engine = Engine()
    engine.register_directory(DATA_DIR)

    stdin = io.StringIO("SELECT COUNT(*) AS n FROM departments;\nexit\n")
    out = io.StringIO()
    code = _shell(engine, "table", out, stdin)
    assert code == 0
    printed = out.getvalue()
    assert "n" in printed
    assert "(1 row)" in printed


def test_shell_handles_multiline_statement(capsys):
    from sqlmini.cli import _shell
    from sqlmini.engine import Engine

    engine = Engine()
    engine.register_directory(DATA_DIR)

    stdin = io.StringIO("SELECT name\nFROM departments\nWHERE id = 1;\nquit\n")
    out = io.StringIO()
    code = _shell(engine, "table", out, stdin)
    assert code == 0
    assert "Engineering" in out.getvalue()
