import atexit
import hashlib
import random
import string
import subprocess
import time
from pathlib import Path

import portalocker

_container_name = None


def generate_random_string(length=8):
    """Generate a random alphanumeric string for container name/password."""

    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def get_container_name():
    """Generate a deterministic container name based on the current directory.
    This ensures each project gets its own persistent container name."""
    cwd_hash = hashlib.md5(Path.cwd().as_posix().encode()).hexdigest()[:8]
    return f"devdb-{cwd_hash}"


def cleanup_container():
    """Stop and remove the container if it exists."""

    global _container_name
    if not _container_name:
        return True

    inspect = subprocess.run(
        ["docker", "inspect", _container_name],
        capture_output=True,
        text=True,
        check=False,
    )

    if inspect.returncode == 0:
        print(f"\n🧹 Cleaning up container: {_container_name}")
        stop = subprocess.run(
            ["docker", "stop", _container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        rm = subprocess.run(
            ["docker", "rm", _container_name],
            capture_output=True,
            text=True,
            check=False,
        )

        if stop.returncode != 0 or rm.returncode != 0:
            print("❌ Failed to clean up container!")
            raise RuntimeError("Docker cleanup failed")

        print(f"\n✅ Container removed: {_container_name}")
        _container_name = None
        return True

    _container_name = None
    return False


def create_postgres_container(ttl):
    """
    Spin up a Postgres container and return the connection string and absolute deadline.
    Args:
        ttl: Time-to-live in seconds (counted from the moment `docker run` is called).

    Returns:
        tuple: (connection_string, deadline_timestamp)

    """
    if ttl <= 0:
        raise ValueError("TTL must be a positive integer")

    global _container_name

    lock_path = Path.cwd() / ".devdb.lock"
    with portalocker.Lock(lock_path, timeout=10) as _lock:
        # 1. Generate a deterministic container name and ensure a clean slate
        container_name = get_container_name()
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        _container_name = container_name

        db_name = "devdb"
        db_user = "devdb"
        db_password = generate_random_string(12)

        # 2. Build the docker run command
        docker_cmd = [
            "docker",
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

        # 3. Run the container
        print(f"🐳 Starting Postgres container: {container_name}")
        result = subprocess.run(docker_cmd, capture_output=True, text=True, check=False)
        start_time = time.time()
        deadline = start_time + ttl

        if result.returncode != 0:
            print("❌ Failed to start container:")
            print(result.stderr)
            raise RuntimeError("Docker run failed")

        container_id = result.stdout.strip()
        print(f"\n✅ Container started with id: {container_id[:12]}")

        # 4. Wait for Postgres to become healthy
        print("⏳ Waiting for Postgres to be ready...")
        for _ in range(30):
            check_cmd = [
                "docker",
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
            check_result = subprocess.run(
                check_cmd, capture_output=True, text=True, check=False
            )
            if "accepting connections" in check_result.stdout:
                print("✅ Your test database is ready!")
                break
            time.sleep(1)
        else:
            print("❌ Timeout waiting for Postgres")
            cleanup_container()
            raise RuntimeError("Postgres did not start in time")

        port_result = subprocess.run(
            ["docker", "port", container_name, "5432"],
            capture_output=True,
            text=True,
            check=False,
        )

        try:
            host_port = port_result.stdout.strip().split(":")[-1]
            if not host_port:
                raise ValueError("Empty port output")
        except ValueError as e:
            cleanup_container()
            raise RuntimeError(f"Could not determine host port: {e}")

        conn_string = (
            f"postgresql://{db_user}:{db_password}@127.0.0.1:{host_port}/{db_name}"
        )

        # 5. Register cleanup on normal exit
        print(f"\nThis container will auto-cleanup in {ttl} seconds.")

        # 6. Output the connection string, deadline
        atexit.register(cleanup_container)
        return conn_string, deadline


def get_container_state(container_name: str) -> str | None:
    """Return the container's state or None if it doesn't exist."""

    status_cmd = ["docker", "inspect", "-f", "{{.State.Status}}", container_name]
    status_result = subprocess.run(
        status_cmd, capture_output=True, text=True, check=False
    )
    state = status_result.stdout.strip()

    if status_result.returncode != 0:
        return None
    return state


def get_container_port(container_name: str) -> str | None:
    """Return the host port or None if not found."""

    port_result = subprocess.run(
        ["docker", "port", container_name, "5432"],
        capture_output=True,
        text=True,
        check=False,
    )
    port = port_result.stdout.strip().split(":")[-1]

    if port_result.returncode != 0 or not port:
        return None
    return port


def get_container_created_at(container_name: str) -> str | None:
    """Return the container creation timestamp or None."""

    created_cmd = ["docker", "inspect", "-f", "{{.Created}}", container_name]
    created_result = subprocess.run(
        created_cmd, capture_output=True, text=True, check=False
    )
    created = created_result.stdout.strip()

    if created_result.returncode != 0:
        return None
    return created


def container_exists(container_name: str) -> bool:
    """Check if a container exists (regardless of state)."""

    inspect = subprocess.run(
        ["docker", "inspect", container_name],
        capture_output=True,
        text=True,
        check=False,
    )

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


if __name__ == "__main__":
    # This is completely ignored when you run uv run devdb start. It only runs if you execute python src/devdb/container.py directly.

    ttl = 10
    create_postgres_container(ttl=ttl)
    try:
        # Keep the main thread alive for manual testing.
        # Sleep for TTL + 1 second. Ctrl+C will interrupt this sleep.
        time.sleep(ttl + 1)
    except KeyboardInterrupt:
        cleanup_container()
