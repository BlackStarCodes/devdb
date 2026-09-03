import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer
import yaml

from devdb.config import load_config
from devdb.container import (
    _force_remove_container,
    _run_docker,
    cleanup_container,
    container_exists,
    create_postgres_container,
    get_container_info,
    get_container_name,
    get_container_ttl_remaining,
)


def _seed_sql(container_name: str, seed_path: Path) -> None:
    """Load a SQL file into the container. Raises RuntimeError on failure."""
    typer.echo(f"📥 Loading SQL seed: {seed_path}")
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
            raise RuntimeError(f"SQL seeding failed: {stderr.decode()}")
    typer.echo("✅ SQL seed loaded successfully.")


def _seed_csv(container_name: str, seed_path: Path, seed_table: str) -> None:
    """Load a CSV file into the container using COPY. Raises RuntimeError on failure."""

    typer.echo(f"📥 Loading CSV seed: {seed_path} into table '{seed_table}'")
    try:
        with open(seed_path, "r") as f:
            reader = csv.reader(f)
            header = next(reader)
    except StopIteration:
        raise RuntimeError("CSV file is empty")

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
            raise RuntimeError(f"CSV seeding failed: {stderr.decode()}")
    typer.echo("✅ CSV seed loaded successfully.")


def _apply_migration(container_name: str, migration_file: Path) -> None:
    """Apply a .sql migration file to the container. Raises RuntimeError on failure."""
    typer.echo(f"📥 Applying migrations from: {migration_file}")

    with open(migration_file, "rb") as f:
        migration_proc = _run_docker(
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
            stdin=f,
        )

        if migration_proc.returncode != 0:
            raise RuntimeError(f"Migration failed: {migration_proc.stderr}")
    typer.echo("✅ Migrations applied successfully!")


def _print_no_container_error() -> None:
    """Print consistent 'no container' error message."""
    typer.echo("❌ No DevDB container found for the current directory!")
    typer.echo(f"   Current directory: {Path.cwd()}")
    typer.echo("💡 Run 'devdb start' to start a new container in this directory.")


def _print_container_info(info: dict, include_ttl: bool = False, ttl: int = 0) -> None:
    """Print container details in a consistent format."""
    if info is None:
        _print_no_container_error()
        return

    state = info.get("state", "unknown")
    if state != "running":
        typer.echo(f"⚠️  Container {info['name']} is not running (status: {state})")
        typer.echo(f"   Project directory: {Path.cwd()}")
        return

    typer.echo(f"✅ Container {info['name']} is running")
    typer.echo(f"   Port: {info.get('port', 'N/A')}")
    typer.echo(f"   Status: {state}")
    if info.get("created_at"):
        typer.echo(f"   Created at: {info['created_at']}")
    typer.echo(f"   Project directory: {Path.cwd()}")

    if include_ttl:
        remaining = get_container_ttl_remaining(info["name"], ttl)
        if remaining is not None:
            typer.echo(f"   Remaining TTL: {remaining}s")

    typer.echo("💡 To stop it, run 'devdb stop'")


__version__ = "0.1.0"

app = typer.Typer(help="DevDB - Instant Isolated Postgres Test Databases")


@app.callback()
def main():
    """DevDB main entry point."""


@app.command()
def start(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force restart: remove existing container and start fresh.",
    ),
):
    """
    Start a fresh Postgres container for the current project.
    If a container is already running, prints its status and exits.
    Use --force to restart an existing container.
    """
    config = load_config()
    ttl = config.get("ttl_seconds", 300)

    if not isinstance(ttl, int) or ttl <= 0:
        raise typer.BadParameter("ttl_seconds must be a positive integer!")

    container_name = get_container_name()
    # --- 1. Check existing container state ---
    info = get_container_info(container_name)

    if info and info["state"] == "running":
        if force:
            typer.echo(f"⚠️  Forcing restart: stopping and removing {container_name}")
            cleanup_container(container_name)
        else:
            _print_container_info(info)
            raise typer.Exit(code=0)

    if info and info["state"] != "running":
        typer.echo(f"🧹 Removing stale container: {container_name}")
        _force_remove_container(container_name)

    # --- 2. Start fresh container ---
    typer.echo("🚀 Starting a fresh Postgres container for your test database...")
    try:
        conn_string, deadline, container_name = create_postgres_container(ttl=ttl)
    except RuntimeError as e:
        typer.echo(f"❌ Failed to start container: {e}")
        raise typer.Exit(code=1)
    remaining = deadline - time.time()

    # --- 3. Print the ready banner (URL is visible here) ---
    typer.echo("\n" + "=" * 50)
    typer.echo("✅ DevDB is ready for use!")
    typer.echo(f"\n🔗 DATABASE_URL: {conn_string}")
    typer.echo("📋 To copy the URL, select it and press Ctrl+Shift+C.")
    typer.echo("\n⚠️  Press Ctrl+C to stop and clean up the container.")
    typer.echo("=" * 50)

    # --- 4. Wait for TTL or interruption ---
    shutdown_reason = "TTL expired"
    try:
        time.sleep(remaining)
    except KeyboardInterrupt:
        typer.echo("\n🛑 Interrupted by user. Cleaning up...")
        shutdown_reason = "interrupted by user"

    # --- 5. Single cleanup block ---
    try:
        cleanup_container(container_name)
        typer.echo(f"\n✅ DevDB shutdown complete ({shutdown_reason}).")
        sys.exit(0)
    except RuntimeError:
        typer.echo("❌ Cleanup failed!")
        sys.exit(1)


@app.command()
def init():
    """Generate a devdb.yaml configuration file in the current directory. Does not overwrite an existing file."""

    config_path = Path("devdb.yaml")

    if config_path.exists():
        typer.echo("⚠️  devdb.yaml already exists! Remove it to regenerate.")
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

    config_path.write_text(commented_content, encoding="utf-8")
    typer.echo(f"✅ Created {config_path}")
    typer.echo("💡 Edit this file to customize your DevDB environment.")


@app.command()
def seed(
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to SQL or CSV file to load into the running database.",
    ),
    table: str | None = typer.Option(
        None, "--table", "-t", help="Target table name (required for CSV files)."
    ),
):
    """
    Load seed data (SQL or CSV) into the running DevDB container.

    The container must be running (started with 'devdb start').
    For SQL files, the entire file is executed via psql.
    For CSV files, the header is read to map columns, and the data is inserted using COPY.
    """

    config = load_config()
    seed_file = file or config.get("seed_file")
    seed_table = table or config.get("seed_table")

    if not seed_file:
        typer.echo(
            "❌ No seed file specified. Provide --file or set seed_file in devdb.yaml"
        )
        raise typer.Exit(code=1)

    seed_path = Path(seed_file).expanduser().resolve()
    if not seed_path.exists():
        typer.echo(f"❌ Seed file not found: {seed_path}")
        raise typer.Exit(code=1)

    container_name = get_container_name()

    check = _run_docker("inspect", "-f", "{{.State.Status}}", container_name)
    if check.returncode != 0 or check.stdout.strip() != "running":
        typer.echo(
            f"❌ '{container_name}' is not running. Start it with 'devdb start' first!"
        )
        raise typer.Exit(code=1)

    suffix = seed_path.suffix.lower()

    try:
        if suffix == ".sql":
            _seed_sql(container_name, seed_path)
        elif suffix == ".csv":
            if not seed_table:
                typer.echo("❌ CSV seeding requires --table or seed_table in config.")
                raise typer.Exit(code=1)
            _seed_csv(container_name, seed_path, seed_table)
        else:
            typer.echo(f"❌ Unsupported file type: {suffix}. Use .sql or .csv file.")
            raise typer.Exit(code=1)
    except RuntimeError as e:
        typer.echo(f"❌ {e}")
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
    typer.echo("🚀 Starting Postgres container for your command...")
    try:
        conn_string, _deadline, container_name = create_postgres_container(ttl=3600)
    except RuntimeError as e:
        typer.echo(f"❌ Failed to start container: {e}")
        raise typer.Exit(code=1)

    # 2. Apply migrations if provided
    if migrations_path:
        migration_file = Path(migrations_path).expanduser().resolve()
        if not migration_file.exists():
            typer.echo(f"❌ Migration file not found: {migration_file}")
            cleanup_container(container_name)
            raise typer.Exit(code=1)

        _apply_migration(container_name, migration_file)

    # 3. Prepare env and run command
    env = os.environ.copy()
    env["DATABASE_URL"] = conn_string
    typer.echo(f"\n🔗 DATABASE_URL={conn_string}")
    typer.echo(f"▶️  Running: {' '.join(command)}")

    cmd0 = shutil.which(command[0])
    if cmd0 is None:
        typer.echo(f"❌ Command not found: {command[0]}")
        cleanup_container(container_name)
        raise typer.Exit(code=1)
    resolved_command = [cmd0] + command[1:]

    child_proc = subprocess.Popen(
        resolved_command,
        env=env,
        stdout=None,
        stderr=None,
        text=True,
    )
    try:
        child_proc.wait()
        returncode = child_proc.returncode
    except KeyboardInterrupt:
        typer.echo("\n🛑 Interrupted by the user. Cleaning up...")
        child_proc.terminate()
        child_proc.wait()
        cleanup_container(container_name)
        raise typer.Exit(code=130)

    cleanup_container(container_name)

    if returncode != 0:
        typer.echo(f"❌ Command exited with code: {returncode}")
    else:
        typer.echo("✅ Command completed successfully.")
    raise typer.Exit(code=returncode)


@app.command()
def status():
    """Show the current container state (running/port/TTL) for the current directory."""

    container_name = get_container_name()
    info = get_container_info(container_name)

    if info is None:
        _print_no_container_error()
        raise typer.Exit(code=1)

    config = load_config()
    ttl = config.get("ttl_seconds", 300)
    _print_container_info(info, include_ttl=True, ttl=ttl)


@app.command()
def stop():
    """Stop and remove the container for the current directory."""

    container_name = get_container_name()

    if not container_exists(container_name):
        _print_no_container_error()
        raise typer.Exit(code=1)

    if cleanup_container(container_name):
        typer.echo(f"✅ Stopped and removed {container_name}")
        raise typer.Exit(code=0)
    else:
        typer.echo(f"❌ Failed to stop container: {container_name}")
        raise typer.Exit(code=1)


@app.command()
def version():
    """Show the version and exit."""
    typer.echo(f"DevDB version {__version__}")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
