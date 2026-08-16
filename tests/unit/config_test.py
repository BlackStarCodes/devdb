from pathlib import Path

import pytest

from devdb.config import load_config


def test_load_config_defaults(temp_project_dir):
    """Test that config returns defaults when no devdb.yaml exists."""
    config = load_config()
    assert config["ttl_seconds"] == 300
    assert config["migrations_path"] is None
    assert config["seed_file"] is None
    assert config["seed_table"] is None


def test_load_config_with_user_values(temp_project_dir):
    """Test that user values override defaults."""
    config_path = Path("devdb.yaml")
    config_path.write_text("""
ttl_seconds: 60
seed_file: test.sql
seed_table: users
""")
    config = load_config()
    assert config["ttl_seconds"] == 60
    assert config["seed_file"] == "test.sql"
    assert config["seed_table"] == "users"
    # Defaults not overridden should remain
    assert config["migrations_path"] is None


def test_load_config_partial_override(temp_project_dir):
    """Test that partial YAML only overrides specified fields."""
    config_path = Path("devdb.yaml")
    config_path.write_text("""
seed_file: custom.sql
""")
    config = load_config()
    assert config["ttl_seconds"] == 300
    assert config["seed_file"] == "custom.sql"
    assert config["seed_table"] is None


def test_load_config_malformed_yaml(temp_project_dir):
    """Test that malformed YAML raises an exception."""
    import yaml

    config_path = Path("devdb.yaml")
    config_path.write_text("invalid: [yaml")

    with pytest.raises(yaml.YAMLError):
        load_config()
