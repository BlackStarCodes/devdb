import subprocess

from conftest import devdb_cmd


def test_status_when_no_container(test_project_dir):
    result = subprocess.run(
        devdb_cmd("status"), capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "No DevDB container found for the current directory" in result.stdout


def test_status_when_running(devdb_start):
    _proc, _db_url, _container_name = devdb_start

    result = subprocess.run(
        devdb_cmd("status"), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "Container" in result.stdout
    assert "is running" in result.stdout
    assert "Port:" in result.stdout
    assert "Created at:" in result.stdout


def test_stop_when_no_container(test_project_dir):
    result = subprocess.run(
        devdb_cmd("stop"), capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "No DevDB container found for the current directory" in result.stdout


def test_stop_when_running(devdb_start):
    _proc, _db_url, container_name = devdb_start

    result = subprocess.run(
        devdb_cmd("stop"), capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    assert "Stopped and removed" in result.stdout

    check = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={container_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert container_name not in check.stdout
