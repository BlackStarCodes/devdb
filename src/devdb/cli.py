import csv
import os
import subprocess
import time
from pathlib import Path

import typer
import yaml

from devdb.config import load_config
from devdb.container import (
    cleanup_container,
    create_postgres_container,
    get_container_name,
)

__version__ = "0.1.0"

app = typer.Typer(help="DevDB - Instant Isolated Postgres Test Databases")


@app.callback()
def main():
    """DevDB main entry point."""


@app.command()
def start():
    """Start a new isolated Postgres test database.

    The container will auto-cleanup after the TTL expires or when you press Ctrl+C.
    """

    config = load_config()
    ttl = config.get("ttl_seconds", 300)

    if not isinstance(ttl, int) or ttl <= 0:
        raise typer.BadParameter("ttl_seconds must be a positive integer!")

    print("🚀 Starting a fresh Postgres container for your test database...")

    try:
        conn_string, deadline = create_postgres_container(ttl=ttl)
    except RuntimeError as e:
        print(f"❌ Failed to start container: {e}")
        raise typer.Exit(code=1)

    remaining = deadline - time.time()

    print("\n" + "=" * 50)
    print("✅ DevDB is ready for use!")
    print(f"\n🔗 DATABASE_URL: {conn_string}")
    print("📋 To copy the URL, select it and press Ctrl+Shift+C.")
    print("\n⚠️  Press Ctrl+C to stop and clean up the container.")
    print("=" * 50)

    try:
        # Sleep for the TTL duration.
        # The cleanup timer will trigger on its own.
        if remaining > 0:
            time.sleep(remaining)

            try:
                cleanup_container()
            except RuntimeError:
                print("❌ Cleanup failed!")
                raise typer.Exit(code=1)
            print("\n✅ DevDB shutdown complete (TTL expired).")
            raise typer.Exit(code=0)

        else:
            print("⚠️  TTL expired during container startup. Cleaning up immediately.")
            try:
                cleanup_container()
            except RuntimeError:
                print("❌ Cleanup failed!")
                raise typer.Exit(code=1)

            raise typer.Exit(code=1)

    except KeyboardInterrupt:
        # Cleanup already handled by signal handler in container.py

        try:
            cleanup_container()
        except RuntimeError:
            print("❌ Cleanup failed!")
            raise typer.Exit(code=1)
        print("\n✅ DevDB shutdown complete! (interrupted by user)")
        raise typer.Exit(code=0)


@app.command()
def init():
    """Generate a devdb.yaml configuration file in the current directory."""

    config_path = Path("devdb.yaml")

    if config_path.exists():
        print("⚠️  devdb.yaml already exists! Remove it to regenerate.")
        raise typer.Exit(code=1)

    template = {
        "ttl_seconds": 300,
        "migrations_path": None,
        "seed_file": None,
        "seed_table": None,
    }

    yaml_content = yaml.dump(template, default_flow_style=False, sort_keys=False)
    commented_content = (
        "# DevDB Configuration\n"
        "# -------------------\n"
        "# ttl_seconds: How long the container should live (in seconds).\n"
        "# migrations_path: Path to your Alembic migrations folder (optional).\n"
        "# seed_file: Path to a .sql or .csv file to seed the database (optional).\n"
        "# seed_table: Required only if seed_file is a .csv (specifies the target table).\n\n"
        + yaml_content
    )

    config_path.write_text(commented_content)
    print(f"✅ Created {config_path}")
    print("💡 Edit this file to customize your DevDB environment.")


@app.command()
def seed(
    file: str | None = typer.Option(
        None, "--file", "-f", help="Path to SQL or CSV file"
    ),
    table: str | None = typer.Option(
        None, "--table", "-t", help="Target table name (required for CSV)"
    ),
):

    config = load_config()
    seed_file = file or config.get("seed_file")
    seed_table = table or config.get("seed_table")

    if not seed_file:
        print(
            "❌ No seed file specified. Provide --file or set seed_file in devdb.yaml"
        )
        raise typer.Exit(code=1)

    seed_path = Path(seed_file).expanduser().resolve()
    if not seed_path.exists():
        print(f"❌ Seed file not found: {seed_path}")
        raise typer.Exit(code=1)

    from devdb.container import get_container_name

    container_name = get_container_name()

    check = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0 or check.stdout.strip() != "running":
        print(
            f"❌ '{container_name}' is not running. Start it with 'devdb start' first!"
        )
        raise typer.Exit(code=1)

    suffix = seed_path.suffix.lower()
    if suffix == ".sql":
        print(f"📥 Loading SQL seed: {seed_path}")
        with open(seed_path, "rb") as f:
            proc = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    container_name,
                    "psql",
                    "-U",
                    "devdb",
                    "-d",
                    "devdb",
                ],
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                print(f"❌ SQL seeding failed: {stderr.decode()}")
                raise typer.Exit(code=1)
        print("✅ SQL seed loaded successfully.")

    elif suffix == ".csv":
        if not seed_table:
            print("❌ CSV seeding requires --table or seed_table in config.")
            raise typer.Exit(code=1)

        print(f"📥 Loading CSV seed: {seed_path} into table '{seed_table}'")
        try:
            with open(seed_path, "r") as f:
                reader = csv.reader(f)
                header = next(reader)
        except StopIteration:
            print("❌ CSV file is empty")
            raise typer.Exit(code=1)
        columns = ", ".join(header)
        copy_cmd = f"COPY {seed_table} ({columns}) FROM STDIN CSV HEADER;"

        cmd = [
            "docker",
            "exec",
            "-i",
            container_name,
            "psql",
            "-U",
            "devdb",
            "-d",
            "devdb",
            "-c",
            copy_cmd,
        ]

        with open(seed_path, "rb") as f:
            proc = subprocess.Popen(
                cmd, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                print(f"❌ CSV seeding failed: {stderr.decode()}")
                raise typer.Exit(code=1)
        print("✅ CSV seed loaded successfully.")
    else:
        print(f"❌ Unsupported file type: {suffix}. Use .sql or .csv file.")
        raise typer.Exit(code=1)


@app.command()
def test(
    command: list[str] = typer.Argument(  # noqa: B008
        ...,
        allow_dash=True,
        help="Command to run (eg., pytest tests/). Use -- before the command.",
    ),
    migrations_path: str | None = typer.Option(
        None,
        "--migrations",
        "-m",
        help="Path to a .sql schema file to apply before running the command.",
    ),
):
    """
    Run a command with DATABASE_URL set to a fresh DevDB container.

    Starts a Postgres container, sets DATABASE_URL, runs your command,
    and destroys the container when the command finishes (even on failure).
    """

    # 1. Start the container
    print("🚀 Starting Postgres container for your command...")
    try:
        conn_string, _deadline = create_postgres_container(ttl=3600)
    except RuntimeError as e:
        print(f"❌ Failed to start container: {e}")
        raise typer.Exit(code=1)

    # 2. Apply migrations if provided
    if migrations_path:
        migration_file = Path(migrations_path).expanduser().resolve()
        if not migration_file.exists():
            print(f"❌ Migration file not found: {migration_file}")
            cleanup_container()
            raise typer.Exit(code=1)

        print(f"📥 Applying migrations from: {migration_file}")
        container_name = get_container_name()

        with open(migration_file, "rb") as f:
            migration_proc = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    container_name,
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "devdb",
                    "-d",
                    "devdb",
                ],
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            _, stderr = migration_proc.communicate()
            if migration_proc.returncode != 0:
                print(f"❌ Migration failed: {stderr.decode()}")
                cleanup_container()
                raise typer.Exit(code=1)
        print("✅ Migrations applied successfully!")

    # 3. Prepare env and run command
    env = os.environ.copy()
    env["DATABASE_URL"] = conn_string
    print(f"\n🔗 DATABASE_URL={conn_string}")
    print(f"▶️  Running: {' '.join(command)}")

    child_proc = subprocess.Popen(
        command,
        env=env,
        stdout=None,
        stderr=None,
        text=True,
    )

    try:
        child_proc.wait()
        returncode = child_proc.returncode
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by the user. Cleaning up...")
        child_proc.terminate()
        child_proc.wait()
        cleanup_container()
        raise typer.Exit(code=130)

    cleanup_container()

    if returncode != 0:
        print(f"❌ Command exited with code: {returncode}")
    else:
        print("✅ Command completed successfully.")
    raise typer.Exit(code=returncode)


@app.command()
def version():
    """Show the version and exit."""
    print(f"DevDB version {__version__}")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
