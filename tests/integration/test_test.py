from conftest import run_devdb


def test_devdb_test_success(test_project_dir):
    """Test that devdb test runs a successful command and cleans up."""

    result = run_devdb("test", "--", "echo", "Hello World")

    assert result.returncode == 0
    assert "Hello World" in result.stdout
    assert "✅ Command completed successfully." in result.stdout


def test_devdb_test_failure(test_project_dir):
    """Test that devdb test propagates failure exit codes."""
    result = run_devdb("test", "--", "python", "-c", "exit(42)")

    assert result.returncode == 42
    assert "❌ Command exited with code: 42" in result.stdout


def test_devdb_test_sets_env_var(test_project_dir):
    """Test that DATABASE_URL is set and accessible in the child process."""

    result = run_devdb(
        "test",
        "--",
        "python",
        "-c",
        "import os; print(os.environ['DATABASE_URL'])",
    )

    assert result.returncode == 0
    assert "postgresql://" in result.stdout
