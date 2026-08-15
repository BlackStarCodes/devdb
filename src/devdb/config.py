from pathlib import Path
import yaml


DEFAULT_CONFIG = {
    "ttl_seconds": 300,
    "migrations_path": None,
    "seed_file": None,
    "seed_table": None,
}


def load_config(path="devdb.yaml"):
    config= DEFAULT_CONFIG.copy()
    config_file = Path(path)

    if config_file.exists():
        with open(config_file, "r") as f:
            user_config = yaml.safe_load(f) or {}
            config.update(user_config)

    return config

