from unittest.mock import MagicMock, patch

from devdb.container import (
    container_exists,
    get_container_created_at,
    get_container_port,
    get_container_state,
)


def test_get_container_state_exists():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "running\n"
        mock_run.return_value = mock_result

        result = get_container_state("devdb-test")
        assert result == "running"


def test_get_container_state_not_exists():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = get_container_state("devdb-test")
        assert result is None


def test_get_container_port_not_found():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = get_container_port("devdb-test")
        assert result is None


def test_get_container_port_found():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0.0.0.0:5433\n"
        mock_run.return_value = mock_result

        result = get_container_port("devdb-test")
        assert result == "5433"


def test_get_container_create_at_success():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "2026-08-19T10:00:00Z\n"
        mock_run.return_value = mock_result

        result = get_container_created_at("devdb-test")
        assert result == "2026-08-19T10:00:00Z"


def test_container_exists_true():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = container_exists("devdb-test")
        assert result is True


def test_container_exists_false():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = container_exists("devdb-test")
        assert result is False
