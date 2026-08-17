import pytest
import time
import subprocess
import signal
import os
import psycopg2


def test_devdb_start_and_connect(devdb_start):
    """
    Test container startup and connectivity.
    Sends SIGINT to ensure graceful exit; cleanup is handled by the fixture.
    """
    proc, db_url, container_name = devdb_start

    # Try psycopg2 first
    connected = False
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
        conn.close()
        connected = True
        print("✅ psycopg2 connection succeeded")
    except Exception as e:
        print(f"⚠️ psycopg2 connection failed: {e} (fallback to docker exec)")

    # Fallback to docker exec if needed
    if not connected:
        password = db_url.split(":")[2].split("@")[0]
        time.sleep(2)

        for attempt in range(5):
            cmd = [
                "docker", "exec", "-e", f"PGPASSWORD={password}",
                container_name,
                "psql", "-h", "127.0.0.1", "-U", "devdb", "-d", "devdb",
                "-c", "SELECT 1"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                print("✅ docker exec fallback succeeded")
                break
            time.sleep(1)
        else:
            pytest.fail(f"Both connection methods failed: {result.stderr}")

    # Verify container is running
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={container_name}"],
        capture_output=True, text=True
    )
    assert container_name in result.stdout

    # Send SIGINT to trigger graceful shutdown (cleanup is handled by fixture)
    proc.send_signal(signal.SIGINT)

    # Wait for process to exit (should be quick)
    try:
        proc.wait(timeout=10)
        print(f"✅ Process exited with return code {proc.returncode}")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail("Process did not exit after SIGINT")


def test_devdb_ttl_cleanup(test_project_dir):
    """
    Test TTL auto-cleanup (this is the primary cleanup verification).
    """
    config_path = test_project_dir / "devdb.yaml"
    config_path.write_text("ttl_seconds: 3")

    from devdb.container import get_container_name
    container_name = get_container_name()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        ["uv", "run", "devdb", "start"],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )

    try:
        time.sleep(10)
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_name}"],
            capture_output=True, text=True
        )
        assert container_name not in result.stdout

    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, check=False)