# DevDB – Fresh Postgres in One Command

[![CI](https://github.com/BlackStarCodes/devdb/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackStarCodes/devdb/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/devdb.svg)](https://badge.fury.io/py/devdb)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**One command. Fresh Postgres. Auto‑cleanup.**

DevDB spins up a fully isolated Postgres container for your integration tests and local development. No manual Docker setup. No orphaned containers. No shared test databases that step on each other.

---

## Quickstart

```bash
# Clone the repo
git clone https://github.com/BlackStarCodes/devdb.git
cd devdb

# Set up the environment
uv venv
source .venv/bin/activate
uv pip install -e .

# Start a fresh database
uv run devdb start
```

You'll get a `DATABASE_URL` in about 3-5 seconds. The container automatically cleans up after the TTL (default 300 seconds) or when you hit `Ctrl+C`.

---

## Configuration

Create a `devdb.yaml` file in your project root:

```yaml
ttl_seconds: 120   # How long the container lives
```

The tool picks up the config automatically. If the file is missing, it falls back to 300 seconds.

---

## How It Works

DevDB generates a container name based on your project directory. Run `devdb start` twice in the same folder, and it replaces the old container with a fresh one. No orphaned containers.

The TTL clock starts the moment `docker run` is called – not after Postgres is ready. So the container lives for exactly the time you specify, regardless of startup jitter.

---

## Commands

| Command | Description |
| :--- | :--- |
| `devdb start` | Start a fresh Postgres container. |
| `devdb --version` | Show the version. |
| `devdb --help` | Show help. |

### Planned Commands (V2)

| Command | Description |
| :--- | :--- |
| `devdb init` | Generate a `devdb.yaml` config file. |
| `devdb seed` | Load SQL or CSV data into the running container. |
| `devdb status` | Show the current container state (running/port/TTL). |
| `devdb test -- pytest tests/` | Start DB, run a command, destroy DB after. |

---

## Edge Cases & Error Handling

- **Docker not running:** DevDB prints a clear error and exits.
- **Port already in use:** The tool finds the next available port starting from 5432.
- **TTL expires during startup:** The tool cleans up immediately and exits.
- **Ctrl+C during startup:** The container is removed gracefully.

---

## Why DevDB?

| Approach | Pros | Cons |
| :--- | :--- | :--- |
| **Raw Docker** | Full control | Manual port mapping, cleanup, and config |
| **Testcontainers** | Great for Python tests | Heavy, requires Python code, not standalone |
| **DevDB** | One command, auto-cleanup, language‑agnostic | Postgres‑only for now |

---

## Development

Clone the repo and install in editable mode:

```bash
git clone https://github.com/BlackStarCodes/devdb.git
cd devdb
uv venv
source .venv/bin/activate
uv pip install -e .
uv sync --dev   # Installs dev dependencies
pre-commit install
```

Run tests:

```bash
uv run pytest tests/ -v
```

Unit tests run fast (no Docker). Integration tests spin up real containers.

---

## Roadmap (V2)

- **Migration runner** – auto-run `alembic upgrade head` or SQL schema files.
- **Custom image support** – allow users to specify `postgres:16` or custom images.
- **MySQL support** – support `mysql:latest` alongside Postgres.

---

## License

MIT