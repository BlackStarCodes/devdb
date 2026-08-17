# DevDB Architecture

## What Is DevDB?

DevDB is a CLI tool that gives you a fresh Postgres database in one command. No manual Docker setup. No cleaning up orphaned containers. Just `devdb start` and you get a `DATABASE_URL` that works.

The core idea is simple: spin up a Postgres container, wait for it to become healthy, print the connection string, and clean up automatically when the TTL expires or you press Ctrl+C. It's designed for integration tests and local development where you need a real database but don't want to manage it yourself.

---

## The Stack

I kept the stack boring and reliable:

- **Language:** Python 3.11+
- **CLI Framework:** Typer – type-hinted, auto-generates `--help`, minimal boilerplate.
- **Container Orchestration:** Docker CLI via `subprocess` – no extra SDK dependencies. Every developer already has Docker installed.
- **Database Image:** `postgres:15-alpine` – small image, fast startup.

---

## Core Components

### `cli.py` – The Command Interface
- Defines the `start` command.
- Loads configuration (`devdb.yaml`) via `config.py`.
- Passes the TTL to the container orchestrator.
- Handles the main thread sleep and `KeyboardInterrupt` (Ctrl+C).

### `container.py` – The Docker Lifecycle
- **Deterministic Naming:** Generates a container name based on the current directory hash. This means each project gets its own stable container name (`devdb-a1b2c3d4`). No more guessing which container belongs to which project.
- **Port Allocation:** Finds an available host port dynamically, starting from 5432.
- **Health Check:** Waits for Postgres to become ready using `pg_isready` inside the container.
- **Absolute Deadline:** Calculates an expiry timestamp (`time.time() + ttl`) immediately after `docker run`. This guarantees the container lives for exactly `ttl` seconds, regardless of how long Postgres takes to start up.
- **Cleanup:** Removes any existing container with the same name (`docker rm -f`) before starting a new one. This ensures a pristine state every time you run `devdb start`.

### `config.py` – Configuration Management
- Loads `devdb.yaml` from the current working directory.
- Falls back to sensible defaults (`ttl_seconds: 300`) if the file is missing.

---

## Lifecycle Flow (TTL & Cleanup)

Here is exactly what happens when you run `devdb start`:

1. The CLI loads `ttl` (e.g., 25 seconds) from `devdb.yaml` (or uses the default).
2. The container orchestrator:
   - Removes any old container with the same deterministic name.
   - Runs `docker run` and **immediately** captures `deadline = time.time() + ttl`.
   - Waits for Postgres to become healthy by polling `pg_isready`.
   - Returns the `deadline` and the connection string to `cli.py`.
3. The CLI calculates `remaining = deadline - time.time()`.
4. **If `remaining > 0`:** The CLI sleeps for `remaining` seconds, then explicitly calls `cleanup_container()`.
5. **If you press Ctrl+C:** The CLI catches `KeyboardInterrupt` and immediately calls `cleanup_container()`.
6. **Safety Net:** `atexit` is registered as a fallback. If the process exits unexpectedly (e.g., a crash), it still attempts to remove the container.

---

## Design Decisions (ADRs)

### ADR 1: Deterministic Container Names
- **The problem:** Random names (`devdb-xyZ12`) made it impossible to know which container belonged to which project.
- **The decision:** Use `hashlib.md5(Path.cwd().as_posix()).hexdigest()[:8]` to generate a stable name per directory.
- **The result:** Running `devdb start` twice in the same folder replaces the old container with a fresh one. No orphaned containers.

### ADR 2: Synchronous Sleep over Threading/Signals
- **The problem:** We initially tried `threading.Timer` and `signal.signal`. Signal handlers in Python are brittle – they cause race conditions and deadlocks.
- **The decision:** Use a single-threaded `time.sleep()` loop with `try/except KeyboardInterrupt`.
- **The result:** The code is deterministic, easy to test, and scales naturally to future multi-container support (if we ever add it).

### ADR 3: Absolute Deadline over Relative Sleep
- **The problem:** Postgres startup time varies (2–10 seconds). A relative `sleep(ttl)` meant the container stayed alive longer than intended.
- **The decision:** Calculate `deadline` immediately after `docker run` and sleep only for the `remaining` time.
- **The result:** The container shuts down exactly `ttl` seconds after the process starts, regardless of startup jitter.

---

## Concurrency & Race Conditions

DevDB uses deterministic container names based on the current working directory (`devdb-{hash}`). This means multiple projects never conflict with each other.

However, running `devdb start` simultaneously in **the same directory** introduces a race condition: two processes could try to remove the existing container and start a new one at the same time. This is a known limitation of the current implementation. The tool handles the common case (single user, single terminal) reliably. For concurrent use, a file-based lock or distributed coordination would be required. This is a deliberate trade-off: simplicity for the common case over complexity for the edge case.

### Failure Handling

The tool handles several failure scenarios:

| Scenario | How DevDB Handles It |
| :--- | :--- |
| **Docker not installed or not running** | `docker run` fails with a clear error; `cli.py` catches `RuntimeError` and exits with code 1. |
| **Postgres fails to become ready** | The health check loop times out after 30 seconds; `cleanup_container()` is called; the tool exits with an error. |
| **TTL cleanup fails** | `cleanup_container()` raises `RuntimeError`; `cli.py` prints an error and exits with code 1. |
| **Ctrl+C during startup** | `KeyboardInterrupt` is caught; `cleanup_container()` is called to remove the container. |
| **Process exits unexpectedly** | `atexit` registers a fallback cleanup to remove the container. |

### Cross-Platform Support

The tool uses `subprocess` with list arguments (no `shell=True`), `pathlib` for file paths, and avoids any system-specific dependencies. It should work on Linux, macOS, and Windows (with Docker Desktop). Signal handling for `SIGINT` (Ctrl+C) is the only area where behavior may vary slightly, but the fallback `atexit` cleanup ensures reliability.

---

## Testing Strategy

We have three layers of tests:

- **Unit tests** (`tests/unit/`): Fast, no Docker. They test the config loader, random string generator, port finder, and container naming logic.
- **Integration tests** (`tests/integration/`): Slower, use real Docker. They spin up a container, connect to it, run a query, and verify cleanup works via both Ctrl+C and TTL expiry. These tests use retry loops instead of hardcoded sleeps, so they are not flaky.
- **Error path tests** (`tests/integration/test_errors.py`): Mock `subprocess.run` to simulate Docker being unavailable, ensuring the tool fails gracefully.

The integration tests run in isolated temporary directories, so they never interfere with each other. Each test gets its own deterministic container name, preventing cross-test contamination.

---

## Current Status

| Feature | Status |
| :--- | :--- |
| `devdb start` – spins up Postgres | ✅ Complete |
| Deterministic container names | ✅ Complete |
| Dynamic port allocation | ✅ Complete |
| Absolute TTL with auto-cleanup | ✅ Complete |
| Ctrl+C graceful shutdown | ✅ Complete |
| Config loading (`devdb.yaml`) | ✅ Complete |
| Unit tests (config + utilities) | ✅ Complete |
| Integration tests (`devdb start`) | ✅ Complete |
| Error path tests (Docker down) | ✅ Complete |
| `devdb init` (config generator) | ⏳ Planned |
| `devdb seed` (SQL/CSV loading) | ⏳ Planned |
| CI Pipeline (GitHub Actions) | ⏳ Planned |
| `devdb status` – check container state | ⏳ Planned |
| `devdb test` – run tests with DB lifecycle | ⏳ Planned |

---

## Project Structure

I use a `src/` layout to prevent import issues when running tests.

```
devdb/
├── src/
│ └── devdb/
│       ├── init.py
│       ├── cli.py
│       ├── container.py
│       └── config.py
├── tests/
│   ├── unit/
│   │ ├── test_config.py
│   │ └── test_container_utils.py
│   └── integration/
│       ├── test_start.py
│       └── test_errors.py
├── docs/
│ └── ARCHITECTURE.md
├── pyproject.toml
├── .pre-commit-config.yaml
├── .gitignore
└── README.md
```

---

## Why This Architecture?

I optimized for three things:

1. **Reliability** – no flaky tests, no orphaned containers, no race conditions.
2. **Simplicity** – minimal dependencies, straightforward code, easy to debug.
3. **Developer experience** – clear output, intuitive commands, a tool that just works.

I avoided over-engineering. No ORM, no async, no microservices. Just a CLI tool that orchestrates Docker and gives you a Postgres database on demand.

*Last updated: 17 August 2026*