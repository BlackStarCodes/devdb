from pathlib import Path

from conftest import exec_psql, run_devdb


def test_seed_sql(devdb_start):
    """Test loading a SQL file into the running container."""

    _proc, _db_url, container_name = devdb_start

    # 1. Create a temporary SQL file
    sql_file = Path("seed.sql")
    sql_file.write_text("""
CREATE TABLE test_sql (id SERIAL PRIMARY KEY, name TEXT);
INSERT INTO test_sql (name) VALUES ('ALICE'), ('BOB');

""")

    # 2. Run the seed command
    result = run_devdb("seed", "--file", str(sql_file))

    assert result.returncode == 0
    assert "✅ SQL seed loaded successfully." in result.stdout

    # 3. Verify the data was loaded
    check_result = exec_psql(container_name, "SELECT COUNT(*) FROM test_sql;")

    assert check_result.returncode == 0
    assert "2" in check_result.stdout


def test_seed_csv(devdb_start):
    """Test loading a CSV file into the running container."""

    _proc, _db_url, container_name = devdb_start

    # 1. Create a table for CSV.
    create_table = exec_psql(
        container_name,
        "CREATE TABLE test_csv (id SERIAL PRIMARY KEY, name TEXT, age INT);",
    )

    assert create_table.returncode == 0

    # 2. Create a temporary CSV file
    csv_file = Path("seed.csv")
    csv_file.write_text("name,age\nCharlie,30\nDiana,25\n")

    # 3. Run the seed command
    result = run_devdb("seed", "--file", str(csv_file), "--table", "test_csv")

    assert result.returncode == 0
    assert "✅ CSV seed loaded successfully." in result.stdout

    # 4. Verify the data was loaded
    check_result = exec_psql(container_name, "SELECT COUNT(*) FROM test_csv;")

    assert check_result.returncode == 0
    assert "2" in check_result.stdout
