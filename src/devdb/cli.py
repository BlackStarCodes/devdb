import time

import typer

from devdb.config import load_config
from devdb.container import cleanup_container, create_postgres_container

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
    from pathlib import Path

    import yaml

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
def version():
    """Show the version and exit."""
    print(f"DevDB version {__version__}")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
