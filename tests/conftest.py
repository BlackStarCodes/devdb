import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from devdb.container import get_container_name


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

        container_name = get_container_name()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            devdb_cmd("start"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Wait for container to be running AND Postgres to accept TCP connections
        for _ in range(30):
            state_result = run_docker(
                "inspect", "-f", "{{.State.Status}}", container_name
            )

            if state_result.stdout.strip() != "running":
                time.sleep(1)
                continue

            pg_result = run_docker(
                "exec",
                container_name,
                "pg_isready",
                "-h",
                "127.0.0.1",
                "-p",
                "5432",
                "-U",
                "devdb",
                "-d",
                "devdb",
            )

            if "accepting connections" in pg_result.stdout:
                break
            time.sleep(1)
        else:
            raise AssertionError(
                "Container/Postgres did not become ready within timeout"
            )

        # Get host port

        port_result = run_docker("port", container_name, "5432")
        host_port = port_result.stdout.strip().split(":")[-1]

        # Get password from container
        env_result = run_docker("exec", container_name, "env")

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
            run_docker("rm", "-f", container_name)


def devdb_cmd(*args: str) -> list[str]:
    """Return the base DevDB command with the given arguments."""
    return ["uv", "run", "devdb", *args]


def run_devdb(*args: str, **kwargs) -> subprocess.CompletedProcess:
    """
    Run a DevDB command with standard arguments (capture_output=True, text=True, check=False)
    Additional kwargs are passed through.
    """
    cmd = devdb_cmd(*args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def docker_cmd(*args: str) -> list[str]:
    """Return the base Docker command with the given arguments."""
    return ["docker", *args]


def run_docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    """
    Run a Docker command with standard arguments (capture_output=True, text=True, check=False)
    Additional kwargs are passed through.
    """
    cmd = docker_cmd(*args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def exec_psql(
    container_name: str, query: str, db_name: str = "devdb", user: str = "devdb"
) -> subprocess.CompletedProcess:
    """
    Execute a SQL query inside a DevDB container via psql.
    """

    return run_docker(
        "exec", container_name, "psql", "-U", user, "-d", db_name, "-c", query
    )
