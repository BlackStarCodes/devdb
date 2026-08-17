import pytest
import os
import subprocess
import time
import tempfile
from pathlib import Path


def cleanup_container(container_name):
    """Force remove a container (used in fixtures and finalizers)."""
    if container_name:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, text=True, check=False
        )


@pytest.fixture(scope="function")
def test_project_dir():
    """Create a temporary directory and isolate the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        yield Path(tmpdir)
        os.chdir(old_cwd)


@pytest.fixture(scope="function")
def devdb_start(test_project_dir):
    """
    Starts `devdb start` in a temporary directory.
    Yields (proc, db_url, actual_container_name) and guarantees cleanup.
    """
    container_name = None
    proc = None
    db_url = None

    try:
        # Write config with long TTL
        config_path = test_project_dir / "devdb.yaml"
        config_path.write_text("ttl_seconds: 60")

        from devdb.container import get_container_name
        container_name = get_container_name()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            ["uv", "run", "devdb", "start"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Wait for container to be running AND Postgres to accept TCP connections
        for _ in range(30):
            state_cmd = ["docker", "inspect", "-f", "{{.State.Status}}", container_name]
            state_result = subprocess.run(state_cmd, capture_output=True, text=True, check=False)
            if state_result.stdout.strip() != "running":
                time.sleep(1)
                continue

            pg_cmd = [
                "docker", "exec", container_name,
                "pg_isready", "-h", "127.0.0.1", "-p", "5432", "-U", "devdb", "-d", "devdb"
            ]
            pg_result = subprocess.run(pg_cmd, capture_output=True, text=True, check=False)
            if "accepting connections" in pg_result.stdout:
                break
            time.sleep(1)
        else:
            raise AssertionError("Container/Postgres did not become ready within timeout")

        # Get host port
        port_cmd = ["docker", "port", container_name, "5432"]
        port_result = subprocess.run(port_cmd, capture_output=True, text=True, check=False)
        host_port = port_result.stdout.strip().split(":")[-1]

        # Get password from container
        env_cmd = ["docker", "exec", container_name, "env"]
        env_result = subprocess.run(env_cmd, capture_output=True, text=True, check=False)
        env_lines = env_result.stdout.strip().split("\n")
        db_password = None
        for line in env_lines:
            if line.startswith("POSTGRES_PASSWORD="):
                db_password = line.split("=")[1]
                break

        if db_password is None:
            raise AssertionError("Could not retrieve POSTGRES_PASSWORD from container")

        db_url = f"postgresql://devdb:{db_password}@127.0.0.1:{host_port}/devdb"

        yield proc, db_url, container_name

    finally:
        # Teardown: terminate the process if still running
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        # Force remove the container
        if container_name:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, text=True, check=False
            )