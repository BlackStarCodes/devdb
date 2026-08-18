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
        cur.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob');")
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

    # 3. Assert success
    assert result.returncode == 0, (
        f"Command failed with code {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
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

        cur.execute("SELECT COUNT(*) FROM products;")
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

    # 4. Assert success
    assert result.returncode == 0, (
        f"Command failed with code {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "SUCCESS: Table exists and is empty!" in result.stdout


def test_devdb_test_with_alembic(test_project_dir):
    """
    REAL USE CASE: Run Alembic migrations and then run a test script.
    """
    # 1. Create a minimal Alembic environment
    alembic_dir = Path("migrations")
    alembic_dir.mkdir()
    (alembic_dir / "versions").mkdir()

    # 2. Write env.py (no fileConfig to avoid logging errors)
    (alembic_dir / "env.py").write_text("""
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

target_metadata = None

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
""")

    # 3. Write the migration file with revision variables
    (alembic_dir / "versions" / "001_create_users.py").write_text("""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )

def downgrade():
    op.drop_table('users')        

""")

    # 4. Write the test script
    script = Path("test_alembic.py")
    script.write_text("""
import os
import sys
import psycopg2

def main():
    url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users;")
    count = cur.fetchone()[0]
    conn.close()
    if count == 0:
        print("SUCCESS: Alembic migration applied successfully!")
        return 0
    print("FAIL: Unexpected data in users table")
    return 1


if __name__ == "__main__":
    sys.exit(main())

""")

    # 5. Write the combined runner
    combined_script = Path("combined.py")
    combined_script.write_text("""
import subprocess
import sys
import os

# Generate alembic.ini dynamically with the actual DATABASE_URL
url = os.environ["DATABASE_URL"]

with open("alembic.ini", "w") as f:
    f.write(f\"\"\"[alembic]
script_location = migrations
sqlalchemy.url = {url}
\"\"\")


result = subprocess.run(["alembic", "upgrade", "head"], env=os.environ)
if result.returncode != 0:
    print("Alembic failed")
    sys.exit(result.returncode)


result = subprocess.run(["python", "test_alembic.py"], env=os.environ)
sys.exit(result.returncode)
""")

    # 6. Run devdb test with the combined script
    # The default TTL for `devdb test` is 3600s, which is long enough to outlast
    # the Alembic migration + test script execution.
    result = subprocess.run(
        ["uv", "run", "devdb", "test", "--", "python", str(combined_script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"Command failed with code {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "SUCCESS: Alembic migration applied successfully!" in result.stdout


def test_devdb_test_with_seed_and_test(test_project_dir):
    """
    REAL USE CASE: Apply schema, seed data, and then run tests.
    """

    # 1. Create a schema.sql
    schema = Path("schema.sql")
    schema.write_text("CREATE TABLE products (id SERIAL, name TEXT, price INT);")

    # 2. Create a seed.sql
    seed = Path("seed.sql")
    seed.write_text(
        "INSERT INTO products (name, price) VALUES ('Laptop', 1000), ('Mouse', 30);"
    )

    # 3. Create a test script
    script = Path("seed_test.py")
    script.write_text("""
import os
import sys
import psycopg2


def main():
    url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    conn.close()

    if count == 2:
        print("SUCCESS: Seed data loaded correctly!")
        return 0
    print(f"FAIL: Expected 2 rows, got {count}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
""")

    # 4. Create a runner that: runs schema, seeds, then tests
    runner = Path("runner.py")
    runner.write_text("""
import subprocess
import os
import sys
import re

url = os.environ["DATABASE_URL"]
password = re.search(r'://[^:]+:([^@]+)@', url).group(1)
port = re.search(r':([0-9]+)/', url).group(1)

env = os.environ.copy()
env["PGPASSWORD"] = password

# 1. Apply schema
result = subprocess.run(
["psql", "-h", "127.0.0.1", "-p", port, "-U", "devdb", "-d", "devdb", "-f", "schema.sql"], env=env)


if result.returncode != 0:
    sys.exit(result.returncode)

# 2. Apply seed data    
result = subprocess.run(
    ["psql", "-h", "127.0.0.1", "-p", port, "-U", "devdb", "-d", "devdb", "-f", "seed.sql"],
    env=env,
)
if result.returncode != 0:
    sys.exit(result.returncode)

# 3. Run the test
result = subprocess.run(["python", "seed_test.py"], env=os.environ)
sys.exit(result.returncode)
""")

    result = subprocess.run(
        [
            "uv",
            "run",
            "devdb",
            "test",
            "--",
            "python",
            str(runner),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"Command failed with code {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "SUCCESS: Seed data loaded correctly!" in result.stdout


def test_devdb_test_with_pytest(test_project_dir):
    """
    REAL USE CASE: Run an actual pytest suite against the database.
    """

    # 1. Create a conftest.py with a fixture
    conftest = Path("conftest.py")
    conftest.write_text("""
import pytest
import psycopg2
import os

@pytest.fixture
def db_connection():
    url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(url)
    yield conn
    conn.close()
""")

    # 2. Create a test file
    test_file = Path("test_db.py")
    test_file.write_text("""
import pytest

def test_create_and_query(db_connection):
    cur = db_connection.cursor()
    cur.execute("CREATE TABLE items (id SERIAL, name TEXT);")
    cur.execute("INSERT INTO items (name) VALUES ('Pen'), ('Paper');")
    cur.execute("SELECT COUNT(*) FROM items;")
    count = cur.fetchone()[0]
    assert count == 2
""")

    result = subprocess.run(
        ["uv", "run", "devdb", "test", "--", "pytest", "-v"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"Command failed with code {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "1 passed" in result.stdout or "1 passed" in result.stderr


def test_devdb_test_failure_cleanup(test_project_dir):
    """
    Test that the container is cleaned up even when the test fails.
    """
    script = Path("failing.py")
    script.write_text("""
import sys
print("This test will fail")
sys.exit(1)
""")

    result = subprocess.run(
        ["uv", "run", "devdb", "test", "--", "python", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    # The test should fail (return code 1)
    assert result.returncode == 1, f"Expected return code 1, got {result.returncode}"
    assert "❌ Command exited with code: 1" in result.stdout
