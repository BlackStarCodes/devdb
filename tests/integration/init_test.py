from pathlib import Path

from conftest import run_devdb


def test_init_creates_file(test_project_dir):
    """Test that `devdb init` creates a devdb.yaml file."""
    result = run_devdb("init")

    assert result.returncode == 0
    assert "✅ Created devdb.yaml" in result.stdout

    config_path = Path("devdb.yaml")
    assert config_path.exists()

    content = config_path.read_text()
    assert "ttl_seconds: 300" in content
    assert "migrations_path:" in content
    assert "seed_file:" in content
    assert "seed_table:" in content  # Ensure the correct key is present


def test_init_does_not_overwrite(test_project_dir):
    """Test that `devdb init` does not overwrite an existing devdb.yaml."""
    config_path = Path("devdb.yaml")
    config_path.write_text("ttl_seconds:999")

    result = run_devdb("init")

    assert result.returncode != 0
    assert "already exists" in result.stderr or "already exists" in result.stdout

    # Verify the file was NOT overwritten
    content = config_path.read_text()
    assert "ttl_seconds:999" in content
