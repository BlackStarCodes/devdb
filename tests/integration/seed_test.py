import subprocess
from pathlib import Path


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
    result = subprocess.run(
        ["uv", "run", "devdb", "seed", "--file", str(sql_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "✅ SQL seed loaded successfully." in result.stdout

    # 3. Verify the data was loaded
    check_cmd = [
        "docker",
        "exec",
        container_name,
        "psql",
        "-U",
        "devdb",
        "-d",
        "devdb",
        "-c",
        "SELECT COUNT (*) FROM test_sql;",
    ]

    check_result = subprocess.run(
        check_cmd, capture_output=True, text=True, check=False
    )
    assert check_result.returncode == 0
    assert "2" in check_result.stdout


def test_seed_csv(devdb_start):
    """Test loading a CSV file into the running container."""

    _proc, _db_url, container_name = devdb_start

    # 1. Create a table for CSV.
    create_table_cmd = [
        "docker",
        "exec",
        container_name,
        "psql",
        "-U",
        "devdb",
        "-d",
        "devdb",
        "-c",
        "CREATE TABLE test_csv (id SERIAL PRIMARY KEY, name TEXT, age INT);",
    ]
    subprocess.run(create_table_cmd, capture_output=True, text=True, check=False)

    # 2. Create a temporary CSV file
    csv_file = Path("seed.csv")
    csv_file.write_text("name,age\nCharlie,30\nDiana,25\n")

    # 3. Run the seed command
    result = subprocess.run(
        ["uv", "run", "devdb", "seed", "--file", str(csv_file), "--table", "test_csv"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "✅ CSV seed loaded successfully." in result.stdout

    # 4. Verify the data was loaded
    check_cmd = [
        "docker",
        "exec",
        container_name,
        "psql",
        "-U",
        "devdb",
        "-d",
        "devdb",
        "-c",
        "SELECT COUNT (*) FROM test_csv;",
    ]

    check_result = subprocess.run(
        check_cmd, capture_output=True, text=True, check=False
    )
    assert check_result.returncode == 0
    assert "2" in check_result.stdout
