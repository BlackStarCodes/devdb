from conftest import run_devdb, run_docker


def test_status_when_no_container(test_project_dir):
    result = run_devdb("status")

    assert result.returncode != 0
    assert "No DevDB container found for the current directory" in result.stdout


def test_status_when_running(devdb_start):
    _proc, _db_url, _container_name = devdb_start

    result = run_devdb("status")
    assert result.returncode == 0
    assert "Container" in result.stdout
    assert "is running" in result.stdout
    assert "Port:" in result.stdout
    assert "Created at:" in result.stdout


def test_stop_when_no_container(test_project_dir):
    result = run_devdb("stop")

    assert result.returncode != 0
    assert "No DevDB container found for the current directory" in result.stdout


def test_stop_when_running(devdb_start):
    _proc, _db_url, container_name = devdb_start

    result = run_devdb("stop")

    assert result.returncode == 0
    assert "Stopped and removed" in result.stdout

    check = run_docker("ps", "-a", "--filter", f"name={container_name}")
    assert container_name not in check.stdout
