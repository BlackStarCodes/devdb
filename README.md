# DevDB – Fresh Postgres in One Command

[![CI](https://github.com/BlackStarCodes/devdb/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackStarCodes/devdb/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/devdb-cli.svg)](https://badge.fury.io/py/devdb-cli)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**One command. Fresh Postgres. Auto‑cleanup.**

DevDB spins up a fully isolated Postgres container for your integration tests and local development. No manual Docker setup. Automatically cleans up containers on TTL expiry and normal shutdown. No shared test databases that step on each other.

---

## Prerequisites

- **Docker** – DevDB requires Docker to be installed and running.  
  [Install Docker](https://docs.docker.com/get-docker/)
- **Python 3.11+** – DevDB is built for Python 3.11 and above.
---

## Quickstart
It's recommended to install DevDB in a virtual environment for your project (e.g., using venv or uv venv), but it also works globally.

```bash
# Install DevDB
$ pip install devdb-cli

# Start a fresh database in your project
$ cd your-project
$ devdb init
$ devdb start
```

You'll get a `DATABASE_URL` in about 3-5 seconds. The container automatically cleans up after the TTL (default 300 seconds) or when you hit `Ctrl+C`.

## Example Workflow


```bash
# 1. Initialize configuration (creates devdb.yaml with defaults)
$ devdb init

# 2. Start a fresh Postgres container for this project
$ devdb start
# Output shows DATABASE_URL – copy it if needed
```

> **Note:** `devdb start` runs in the foreground. To run other commands (like `status` or `docker logs`), open a **second terminal** in the same project directory.

```bash
# 3. Run your tests – DATABASE_URL is set automatically in the environment
$ pytest tests/

# 4. When done, stop the container and clean up
$ devdb stop
```

---

## Configuration

Create a `devdb.yaml` file in your project root:

```yaml
ttl_seconds: 120   # How long the container lives
```
Run `devdb init` to generate this file automatically with helpful comments.

The tool picks up the config automatically. If the file is missing, it falls back to 300 seconds.



## How It Works

DevDB generates a container name based on your project directory. Run `devdb start` twice in the same folder, and it replaces the old container with a fresh one. The container is automatically removed on TTL expiry, normal shutdown, or Ctrl+C.

The TTL clock starts the moment `docker run` is called – not after Postgres is ready. So the container lives for exactly the time you specify, regardless of startup jitter.


## Architecture
```
+------------+     +-------------+     +-----------------+
|   User     |---->|  devdb CLI  |---->|  Docker Engine  |
|  (start)   |     |  (cli.py)   |     |  (container.py) |
+------------+     +-------------+     +-----------------+
      |                  |                      |
      v                  v                      v
+------------+     +-------------+     +-----------------+
|  Config    |     |  Postgres   |     |                 |
| devdb.yaml |     |  Container  |     |                 |
+------------+     +-------------+     +-----------------+
```


---
## Features

- **One command** – get a fresh Postgres database without manual Docker setup.
- **Auto‑cleanup** – containers expire after a configurable TTL; no orphaned containers.
- **Isolation** – each project gets its own container; no cross‑project interference.
- **Dynamic ports** – never worry about port conflicts.
- **Concurrency‑safe** – locking ensures multiple `devdb start` calls don't clash.
- **Full lifecycle** – `status`, `stop`, `seed`, `test` – all the commands you need.


## Commands

| Command | Description |
| :--- | :--- |
| `devdb start` | Start a fresh Postgres container (`--force` to restart). |
| `devdb stop` | Stop and remove the current project's container. |
| `devdb status` | Show container state (running/port/creation time). |
| `devdb init` | Generate a `devdb.yaml` config file. |
| `devdb seed` | Load SQL or CSV data into the running container. |
| `devdb test` | Run a command with `DATABASE_URL` set to a fresh container (auto-cleanup). |
| `devdb --version` | Show the version. |
| `devdb --help` | Show help. |



---

### Using `devdb test`

Run your test suite with a fresh database automatically:

```bash
# Run pytest with a temporary database.
$ devdb test -- pytest tests/

# Apply schema migrations before running tests
$ devdb test --migrations schema.sql -- pytest tests
```
> **Note:** Replace `tests/` with the actual path to your test suite (e.g., `my_tests/` or `test/`).

The container starts, DATABASE_URL is set, your command runs, and the container is destroyed on exit (even if the command fails). Your tests should read DATABASE_URL from the environment – no manual configuration is needed. The variable is automatically available to the command you run.


```python
# Your tests must read DATABASE_URL from the environment:
import os, psycopg2
url = os.environ["DATABASE_URL"]
conn = psycopg2.connect(url)
```

### Testing with Alembic

If your project uses Alembic for migrations, add this hook to your `conftest.py`:

```python
import os
from alembic.config import Config
from alembic import command

@pytest.fixture(scope="session", autouse=True)
def run_alembic_migrations():
    if os.environ.get("DATABASE_URL"):
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
        command.upgrade(alembic_cfg, "head")
```
Now devdb test will automatically apply migrations before running your tests.

### Troubleshooting: Module not found

If you see `ModuleNotFoundError: No module named 'your_project'`, set `PYTHONPATH`:

```bash
$ PYTHONPATH=. devdb test -- pytest tests/
```
Or add pythonpath = . to a pytest.ini file in your project root.



---

## Edge Cases & Error Handling

- **Docker not running:** DevDB prints a clear error and exits.
- **Port allocation**: DevDB uses Docker's dynamic port allocation (`-p 127.0.0.1::5432`), which binds to a random available port on localhost only.
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
# Clone the repo
$ git clone https://github.com/BlackStarCodes/devdb.git
$ cd devdb

$ uv venv
$ source .venv/bin/activate

$ uv sync --dev   # Installs package + dev dependencies
$ pre-commit install
```

Run tests:

```bash
$ uv run pytest tests/ -v
```

Unit tests run fast (no Docker). Integration tests spin up real containers.

---

## Roadmap (V2)

- **Migration runner** – auto-run `alembic upgrade head` or SQL schema files.
- **Custom image support** – allow users to specify `postgres:16` or custom images.
- **MySQL support** – support `mysql:latest` alongside Postgres.

---

## FAQ & Troubleshooting

**Q: DevDB says "Docker daemon is not responsive"**  
A: Docker is not running. Start Docker Desktop or run `sudo systemctl start docker` on Linux.

**Q: DevDB fails with "No space left on device"**  
A: Your Docker storage is full. Run `docker system prune -f` to free space, or increase disk size.

**Q: Postgres container does not start (timeout)**  
A: Check `docker logs $(docker ps -qf name=devdb-*)` in a second terminal. Common causes: low disk space, memory constraints, or network issues. Restart Docker and try again.

**Q: How do I inspect the container while it's running?**  
A: Open a second terminal in the same project directory and run `docker ps` or `devdb status`. To see Postgres logs: `docker logs $(docker ps -qf name=devdb-*)`.

**Q: Can I run `devdb start` and then run other commands in the same terminal?**  
A: No – `devdb start` runs in the foreground. Open a second terminal for other commands.

**Q: Does DevDB ever leave orphaned containers?**  
A: DevDB cleans up containers on TTL expiry, Ctrl+C, and normal process exit. In rare cases of hard crashes, the container may remain – run `devdb stop` to remove it manually.

**Q: Can I use a custom Postgres version?**  
A: Not yet – this is planned for V2. Current version uses `postgres:15-alpine`.

**Q: How do I change the TTL after starting?**  
A: Stop the container (`devdb stop`), update `devdb.yaml`, and run `devdb start` again.

**Q: My tests work locally but fail in CI – what's wrong?**  
A: Ensure Docker is available in your CI environment. Check that the CI runner has enough disk space and memory.

## License

MIT