import pytest
import subprocess
from unittest.mock import patch
def test_devdb_start_docker_down(test_project_dir):
    """
    Test graceful failure when Docker daemon is not running.
    We mock `subprocess.run` to simulate Docker being unavailable.
    """
    import devdb.container
    config_path = test_project_dir / "devdb.yaml"
    config_path.write_text("ttl_seconds: 300")
    # Mock subprocess.run for docker calls to simulate "command not found" or "connection refused"
    def mock_run(*args, **kwargs):
        # Check if the command is a docker command
        if isinstance(args[0], list) and args[0] and args[0][0] == "docker":

            return subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="Cannot connect to the Docker daemon"
            )
        
        # Fallback to real run for non-docker calls (like uv)
        return subprocess.run(*args, **kwargs)
    with patch.object(subprocess, 'run', side_effect=mock_run):
        # Since the function raises RuntimeError, we check that.
        from devdb.container import create_postgres_container
        with pytest.raises(RuntimeError) as excinfo:
            create_postgres_container(ttl=300)
        assert "Docker run failed" in str(excinfo.value) or "Cannot connect" in str(excinfo.value)