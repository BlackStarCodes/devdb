import subprocess


def test_devdb_test_success(test_project_dir):
    """Test that devdb test runs a successful command and cleans up."""

    result = subprocess.run(
        ["uv", "run", "devdb", "test", "--", "echo", "Hello World"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Hello World" in result.stdout
    assert "✅ Command completed successfully." in result.stdout


def test_devdb_test_failure(test_project_dir):
    """Test that devdb test propagates failure exit codes."""
    result = subprocess.run(
        ["uv", "run", "devdb", "test", "--", "python", "-c", "exit(42)"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 42
    assert "❌ Command exited with code: 42" in result.stdout


def test_devdb_test_sets_env_var(test_project_dir):
    """Test that DATABASE_URL is set and accessible in the child process."""

    result = subprocess.run(
        [
            "uv",
            "run",
            "devdb",
            "test",
            "--",
            "python",
            "-c",
            "import os; print(os.environ['DATABASE_URL'])",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "postgresql://" in result.stdout
