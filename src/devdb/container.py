import atexit
import hashlib
import random
import socket
import string
import subprocess
import time
from pathlib import Path

_container_name = None


def generate_random_string(length=8):
    """Generate a random alphanumeric string for container name/password."""

    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def find_available_port(start_port=5432, max_attempts=100):
    """Find a free port on the host starting from a given port."""

    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available port found")


def get_container_name():
    """Generate a deterministic container name based on the current directory.
    This ensures each project gets its own persistent container name."""
    cwd_hash = hashlib.md5(Path.cwd().as_posix().encode()).hexdigest()[:8]
    return f"devdb-{cwd_hash}"


def cleanup_container():
    """Stop and remove the container if it exists."""

    global _container_name
    if _container_name:
        print(f"\n 🧹 Cleaning up container: {_container_name}")
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
    return False


def create_postgres_container(ttl):
    """
    Spin up a Postgres container and return the connection string and absolute deadline.
    Args:
        ttl: Time-to-live in seconds (counted from the moment `docker run` is called).

    Returns:
        tuple: (connection_string, deadline_timestamp)

    """
    global _container_name

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

    # 2. Find an available port
    host_port = find_available_port()

    # 3. Build the docker run command
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
        f"{host_port}:5432",
        "postgres:15-alpine",
    ]

    # 4. Run the container
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

    # 5. Wait for Postgres to become healthy
    print("⏳ Waiting for Postgres to be ready...")
    for _ in range(30):
        check_cmd = [
            "docker",
            "exec",
            container_name,
            "pg_isready",
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

    conn_string = (
        f"postgresql://{db_user}:{db_password}@localhost:{host_port}/{db_name}"
    )

    # 6. Register cleanup on normal exit
    print(f"\nThis container will auto-cleanup in {ttl} seconds.")

    # 7. Output the connection string, deadline
    atexit.register(cleanup_container)
    return conn_string, deadline


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
