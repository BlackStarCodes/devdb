import atexit
import functools
import hashlib
import secrets
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import portalocker
import psycopg2
import typer


def generate_random_string(length=8) -> str:
    """Generate a cryptographically secure random string."""
    return secrets.token_urlsafe(length)[:length]


def get_container_name() -> str:
    """Generate a deterministic container name based on the current directory.
    This ensures each project gets its own persistent container name."""
    cwd_hash = hashlib.md5(Path.cwd().as_posix().encode()).hexdigest()[:8]
    return f"devdb-{cwd_hash}"


def _run_docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    """Run a docker command with standard arguments. Extra kwargs passed to subprocess.run."""
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, **kwargs
    )


def cleanup_container(container_name: str) -> bool:
    """
    Stop and remove the container if it exists. Idempotent – safe to call multiple times.
    Raises RuntimeError if the container exists but cannot be removed.
    """
    if not container_name:
        return True

    # Check if container exists
    inspect = _run_docker("inspect", container_name)
    if inspect.returncode != 0:
        return True

    typer.echo(f"\n🧹 Cleaning up container: {container_name}")
    _run_docker("stop", container_name)
    rm = _run_docker("rm", "-f", container_name)

    if rm.returncode != 0:
        # If rm fails, check if it's because the container is already gone
        inspect_again = _run_docker("inspect", container_name)
        if inspect_again.returncode != 0:
            # It's already gone – success
            return True
        # Otherwise, it's a genuine failure
        typer.echo("❌ Failed to clean up container!")
        raise RuntimeError("Docker cleanup failed")

    typer.echo(f"✅ Container removed: {container_name}")
    return True


def _force_remove_container(container_name: str) -> None:
    """Force‑remove any existing container with the given name. Idempotent; does nothing if it doesn't exist."""
    _run_docker("rm", "-f", container_name)


def _wait_for_postgres_ready(container_name: str, db_user: str, db_name: str) -> None:
    """Wait for pg_isready to succeed (up to 30 attempts). Returns None on success, raises on timeout."""

    typer.echo("⏳ Waiting for Postgres to be ready...")
    for _ in range(30):
        check_cmd = [
            "exec",
            container_name,
            "pg_isready",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            db_user,
            "-d",
            db_name,
        ]
        check_result = _run_docker(*check_cmd)

        if "accepting connections" in check_result.stdout:
            typer.echo("✅ Your test database is ready!")
            return
        time.sleep(1)

    cleanup_container(container_name)
    raise RuntimeError(
        f"Postgres did not start within 30 seconds. Container: {container_name}."
    )


def _verify_host_connectivity(
    container_name: str, host_port: str, db_user: str, db_password: str, db_name: str
) -> None:
    """Verify host can connect via psycopg2 (up to 5 attempts). Raises RuntimeError on failure."""
    docker_info = _run_docker("info")
    if docker_info.returncode != 0:
        raise RuntimeError("Docker daemon is not responsive. Please restart Docker.")

    for _ in range(5):
        try:
            conn = psycopg2.connect(
                host="127.0.0.1",
                port=host_port,
                user=db_user,
                password=db_password,
                dbname=db_name,
            )
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(0.5)

    # This check prevents flaky CI failures where the container is internally ready
    # but the host port hasn't propagated yet.
    typer.echo("❌ Host connectivity test failed.")
    cleanup_container(container_name)
    raise RuntimeError(
        f"Host could not connect to Postgres on port {host_port} after 5 attempts."
        "Please check Docker networking or restart the Docker daemon."
    )


def _acquire_lock() -> portalocker.Lock:
    """Acquire a file-based lock for the current project directory."""
    lock_path = Path.cwd() / ".devdb.lock"
    return portalocker.Lock(lock_path, timeout=10)


def _run_container(
    container_name: str, db_name: str, db_user: str, db_password: str, ttl: int
) -> tuple[str, float]:
    """
    Run the Postgres container. Raises RuntimeError if `docker run` fails.
    Returns:
        tuple: (container_id, deadline_timestamp)
    """
    docker_cmd = [
        "run",
        "-d",
        "--name",
        container_name,
        "-e",
        f"POSTGRES_DB={db_name}",
        "-e",
        f"POSTGRES_USER={db_user}",
        "-e",
        f"POSTGRES_PASSWORD={db_password}",
        "-p",
        "5432",
        "postgres:15-alpine",
    ]

    typer.echo(f"🐳 Starting Postgres container: {container_name}")
    result = _run_docker(*docker_cmd)
    start_time = time.time()
    deadline = start_time + ttl

    if result.returncode != 0:
        typer.echo("❌ Failed to start container:")
        typer.echo(result.stderr)
        raise RuntimeError("Docker run failed")

    container_id = result.stdout.strip()
    typer.echo(f"\n✅ Container started with id: {container_id[:12]}")
    return container_id, deadline


def create_postgres_container(ttl: int) -> tuple[str, float, str]:
    """
    Spin up a Postgres container and return the connection string, deadline, and name.
    Raises ValueError if ttl <= 0; raises RuntimeError on Docker or connectivity failures.
    Args:
        ttl: Time-to-live in seconds (counted from the moment `docker run` is called).
    Returns:
        tuple: (connection_string, deadline_timestamp, container_name)
    """
    if ttl <= 0:
        raise ValueError("TTL must be a positive integer")

    with _acquire_lock():
        container_name = get_container_name()
        _force_remove_container(container_name)

        db_name = "devdb"
        db_user = "devdb"
        db_password = generate_random_string(12)

        _, deadline = _run_container(container_name, db_name, db_user, db_password, ttl)

        _wait_for_postgres_ready(container_name, db_user, db_name)

        host_port = get_container_port(container_name)
        if host_port is None:
            typer.echo("❌ Could not determine host port.")
            cleanup_container(container_name)
            raise RuntimeError("Could not determine host port")

        _verify_host_connectivity(
            container_name, host_port, db_user, db_password, db_name
        )

        conn_string = (
            f"postgresql://{db_user}:{db_password}@127.0.0.1:{host_port}/{db_name}"
        )
        typer.echo(f"\nThis container will auto-cleanup in {ttl} seconds.")

        atexit.register(functools.partial(cleanup_container, container_name))
        return conn_string, deadline, container_name


def get_container_state(container_name: str) -> str | None:
    """Return the container's state or None if it doesn't exist."""

    status_cmd = ["inspect", "-f", "{{.State.Status}}", container_name]
    status_result = _run_docker(*status_cmd)
    state = status_result.stdout.strip()

    if status_result.returncode != 0:
        return None
    return state


def get_container_port(container_name: str) -> str | None:
    """Return the host port or None if not found."""

    port_result = _run_docker("port", container_name, "5432")

    if port_result.returncode != 0 or not port_result.stdout.strip():
        return None
    return port_result.stdout.strip().split(":")[-1]


def get_container_created_at(container_name: str) -> str | None:
    """Return the container creation timestamp or None."""

    created_cmd = ["inspect", "-f", "{{.Created}}", container_name]
    created_result = _run_docker(*created_cmd)
    created = created_result.stdout.strip()

    if created_result.returncode != 0:
        return None
    return created


def container_exists(container_name: str) -> bool:
    """Check if a container exists (regardless of state)."""

    inspect = _run_docker("inspect", container_name)

    return inspect.returncode == 0


def get_container_info(container_name: str) -> dict | None:
    """Return a dict with state, port, created_at, or None if container doesn't exist."""

    state = get_container_state(container_name)
    if state is None:
        return None

    return {
        "name": container_name,
        "state": state,
        "port": get_container_port(container_name),
        "created_at": get_container_created_at(container_name),
    }


def get_container_ttl_remaining(container_name: str, ttl: int) -> int | None:
    """Return seconds remaining until TTL expiry, or None if container doesn't exist."""
    created_at = get_container_created_at(container_name)
    if created_at is None:
        return None
    created_ts = datetime.fromisoformat(created_at)
    elapsed = (datetime.now(UTC) - created_ts).total_seconds()
    return max(0, int(ttl - elapsed))


if __name__ == "__main__":
    # This is completely ignored when you run uv run devdb start. It only runs if you execute python src/devdb/container.py directly.

    ttl = 10
    create_postgres_container(ttl=ttl)
    container_name = get_container_name()
    try:
        # Keep the main thread alive for manual testing.
        # Sleep for TTL + 1 second. Ctrl+C will interrupt this sleep.
        time.sleep(ttl + 1)
    except KeyboardInterrupt:
        cleanup_container(container_name)
