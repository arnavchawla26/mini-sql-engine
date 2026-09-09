"""End-to-end scenarios against the example fixtures in examples/data/."""


def test_tables_loaded_from_directory(examples_engine):
    assert examples_engine.table_names() == ["departments", "employees"]
    assert len(examples_engine.table("employees")) == 12
    assert len(examples_engine.table("departments")) == 4


def test_top_paid_employee_per_department(examples_engine):
    result = examples_engine.run(
        "SELECT d.name AS department, e.name AS employee, e.salary "
        "FROM employees e "
        "JOIN departments d ON e.department_id = d.id "
        "WHERE e.is_manager = TRUE "
        "ORDER BY e.salary DESC"
    )
    assert result.columns == ["department", "employee", "salary"]
    assert result.rows[0] == ("Engineering", "Ava Chen", 142000)


def test_average_salary_by_department_sorted_desc(examples_engine):
    result = examples_engine.run(
        "SELECT d.name AS department, COUNT(*) AS headcount, AVG(e.salary) AS avg_salary "
        "FROM employees e JOIN departments d ON e.department_id = d.id "
        "GROUP BY d.name "
        "ORDER BY avg_salary DESC"
    )
    assert result.columns == ["department", "headcount", "avg_salary"]
    top_department = result.rows[0][0]
    assert top_department == "Engineering"


def test_departments_over_budget_threshold_with_having(examples_engine):
    result = examples_engine.run(
        "SELECT d.name, SUM(e.salary) AS payroll "
        "FROM employees e JOIN departments d ON e.department_id = d.id "
        "GROUP BY d.name "
        "HAVING SUM(e.salary) > 400000 "
        "ORDER BY payroll DESC"
    )
    names = [r[0] for r in result.rows]
    assert names == ["Engineering"]


def test_employee_with_no_department_is_excluded_by_inner_join(examples_engine):
    result = examples_engine.run(
        "SELECT e.name FROM employees e JOIN departments d ON e.department_id = d.id"
    )
    names = {r[0] for r in result.rows}
    assert "Kira Petrova" not in names


def test_employee_with_no_department_kept_by_left_join(examples_engine):
    result = examples_engine.run(
        "SELECT e.name, d.name AS dept "
        "FROM employees e LEFT JOIN departments d ON e.department_id = d.id "
        "WHERE e.name = 'Kira Petrova'"
    )
    assert result.rows == [("Kira Petrova", None)]


def test_limit_and_order_together(examples_engine):
    result = examples_engine.run("SELECT name FROM employees ORDER BY salary DESC LIMIT 3")
    assert [r[0] for r in result.rows] == ["Ava Chen", "Liam O'Sullivan", "Ben Ortiz"]


def test_multi_condition_where(examples_engine):
    result = examples_engine.run(
        "SELECT name FROM employees WHERE salary >= 90000 AND is_manager = FALSE"
    )
    assert {r[0] for r in result.rows} == {"Ben Ortiz", "Carla Novak", "Farhan Iqbal", "Liam O'Sullivan"}
