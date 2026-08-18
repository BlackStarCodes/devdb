import subprocess
from pathlib import Path


def test_devdb_test_real_db_usage(test_project_dir):
    """
    REAL USE CASE: Run a Python script that connects to the DB, creates a table,
    inserts data, and queries it. The script must exit with 0 on success.
    """

    # 1. Create a python script with proper error handling
    script = Path("real_test.py")
    script.write_text("""
import os
import sys
import psycopg2

def main():
    try:
        url = os.environ["DATABASE_URL"]
        if not url:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            return 1

        conn = psycopg2.connect(url)
        cur = conn.cursor()

        cur.execute("CREATE TABLE users (id SERIAL, name TEXT);")
        cur.execute("INSERT INTO users (name) VALUES ('ALICE'), ('BOB');")
        cur.execute("SELECT COUNT(*) FROM users;")
        count = cur.fetchone()[0]

        conn.close()

        if count != 2:
            print(f"ERROR: Expected 2 rows, got {count}", file=sys.stderr)
            return 1
        print("SUCCESS: DB works perfectly!")
        return 0

    except psycopg2.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

""")

    # 2. Run the script via devdb test
    result = subprocess.run(
        ["uv", "run", "devdb", "test", "--", "python", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    # Debug output (visible when test fails)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    # 3. Assert success
    assert result.returncode == 0, (
        f"Command failed code {result.returncode} with stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "SUCCESS: DB works perfectly!" in result.stdout


def test_devdb_test_with_migrations(test_project_dir):
    """
    REAL USE CASE: Apply a schema migration (SQL file) before running the command.
    """

    # 1. Create a schema.sql file
    schema = Path("schema.sql")
    schema.write_text("""
CREATE TABLE products (id SERIAL PRIMARY KEY, name TEXT, price INT);
""")

    # 2. Create a python script that uses the schema
    script = Path("app_test.py")
    script.write_text("""
import os
import sys
import psycopg2


def main():
    try:
        url = os.environ["DATABASE_URL"]
        if not url:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            return 1
        conn = psycopg2.connect(url)
        cur = conn.cursor()

        cur.execute("SELECT COUNT (*) FROM products;")
        count = cur.fetchone()[0]
        conn.close()

        if count != 0:
            print(f"ERROR: Expected 0 rows, got {count}", file=sys.stderr)
            return 1

        print("SUCCESS: Table exists and is empty!")
        return 0

    except psycopg2.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
        
""")

    # 3. Run the command with --migrations
    result = subprocess.run(
        [
            "uv",
            "run",
            "devdb",
            "test",
            "--migrations",
            str(schema),
            "--",
            "python",
            str(script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # Debug output (visible when test fails)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    # 4. Assert success
    assert result.returncode == 0, (
        f"Command failed with return code {result.returncode}"
    )
    assert "SUCCESS: Table exists and is empty!" in result.stdout
