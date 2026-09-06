   # DevDB Architecture

   ## What Is DevDB?

   DevDB is a CLI tool that gives you a fresh Postgres database in one command. No manual Docker setup. Automatically cleans up containers on TTL expiry and normal shutdown. Just `devdb start` and you get a `DATABASE_URL` that works.

   The core idea: spin up a Postgres container, wait for it to become healthy, print the connection string, and clean up automatically when the TTL expires or you press Ctrl+C. It's designed for integration tests and local development where you need a real database but don't want to manage it yourself.

   ---

   ## The Stack

   I kept the stack boring and reliable:

   - **Language:** Python 3.11+
   - **CLI Framework:** Typer – type-hinted, auto-generates `--help`, minimal boilerplate. All user output goes through `typer.echo` for consistent encoding.
   - **Container Orchestration:** Docker CLI via `subprocess` – no extra SDK dependencies. Every developer already has Docker installed. Commands are built as lists (no `shell=True`) for security.
   - **Database Image:** `postgres:15-alpine` – small image, fast startup.

   ---

   ## Core Components

   ### `cli.py` – The Command Interface
   - Defines all commands: `start`, `stop`, `status`, `init`, `seed`, `test`, `version`.
   - Loads configuration (`devdb.yaml`) via `config.py`.
   - Uses `_safe_cleanup` helper to consistently handle container removal errors.
   - Handles the main thread sleep and `KeyboardInterrupt` (Ctrl+C).
   - Uses `_print_container_info` to display running container details (including TTL).
   - Uses `_print_no_container_error` for consistent error messages when no container exists.

   ### `container.py` – The Docker Lifecycle
   - **Deterministic Naming:** Generates a container name based on the current directory hash (`devdb-{hash}`). Each project gets its own stable name.
   - **Port Allocation:** Uses `-p 127.0.0.1::5432` to bind to a random available port on localhost only – **security‑critical**.
   - **Health Check:** Waits for Postgres to become ready using `pg_isready` inside the container.
   - **Absolute Deadline:** Calculates an expiry timestamp (`time.time() + ttl`) immediately after `docker run`. The container lives exactly `ttl` seconds, regardless of startup jitter.
   - **Cleanup:** Removes any existing container with the same name (`docker rm -f -v`) before starting a new one. The `-v` flag ensures anonymous volumes are also deleted.
   - **Idempotent Cleanup:** `cleanup_container` checks if the container exists; if not, it returns `True` early – safe to call multiple times.
   - **Error Handling:** All cleanup paths go through `_safe_cleanup`, which catches `RuntimeError` and prints a friendly message.
   - **Force Removal**: _force_remove_container performs a silent docker rm -f -v without printing output – used for stale containers before a fresh start.


   ### `config.py` – Configuration Management

   - Loads `devdb.yaml` from the current working directory.
   - Falls back to sensible defaults (`ttl_seconds: 300`) if the file is missing.
   - Supports custom `migrations_path`, `seed_file`, `seed_table` (used by `seed` and `test`).

   ### `devdb test` – CI/CD Integration

   - Starts a Postgres container, sets `DATABASE_URL` in the environment, runs the user’s command (e.g., `pytest`), and destroys the container on completion (even if the command fails).
   - Uses a long TTL (3600s) to outlast any test suite.
   - Supports an optional `--migrations` flag to apply a `.sql` schema before running the command.
   - Exit codes are propagated, making it safe for CI pipelines.

   ---

   ## Lifecycle Flow (TTL & Cleanup)

   Here is exactly what happens when you run `devdb start`:

   1. The CLI loads `ttl` from `devdb.yaml` (or default 300s).
   2. The container orchestrator:
      - Acquires a file‑based lock (`portalocker`) to prevent concurrent `start` in the same directory.
      - Removes any old container with the same name (`_force_remove_container`).
      - Runs `docker run` with `-p 127.0.0.1::5432` and captures `deadline = time.time() + ttl`.
      - Waits for Postgres to become healthy by polling `pg_isready` (up to 30s).
      - Verifies host connectivity via `psycopg2` (5 attempts) and prints a helpful error if it fails.
      - Returns the `deadline` and the connection string to `cli.py`.
   3. The CLI calculates `remaining = deadline - time.time()`.
   4. **If `remaining > 0`:** the CLI sleeps for `remaining` seconds, then calls `_safe_cleanup()`.
   5. **If you press Ctrl+C:** the CLI catches `KeyboardInterrupt` and immediately calls `_safe_cleanup()`.
   6. **Safety Net:** `atexit` is registered as a fallback. If the process exits unexpectedly, it still attempts to remove the container.

   ---

   ## Design Decisions (ADRs)

   ### ADR 1: Deterministic Container Names
   - **Problem:** Random names made it impossible to know which container belonged to which project.
   - **Decision:** Use `hashlib.md5(Path.cwd().as_posix()).hexdigest()[:8]` to generate a stable name per directory.
   - **Result:** Running `devdb start` twice in the same folder replaces the old container with a fresh one. No orphaned containers.

   ### ADR 2: Synchronous Sleep over Threading/Signals
   - **Problem:** `threading.Timer` and `signal.signal` caused race conditions and deadlocks.
   - **Decision:** Use a single‑threaded `time.sleep()` loop with `try/except KeyboardInterrupt`.
   - **Result:** Deterministic, easy to test, and scales naturally to future multi‑container support.

   ### ADR 3: Absolute Deadline over Relative Sleep
   - **Problem:** Postgres startup time varies (2–10s). A relative `sleep(ttl)` meant the container stayed alive longer than intended.
   - **Decision:** Calculate `deadline` immediately after `docker run` and sleep only for the `remaining` time.
   - **Result:** The container shuts down exactly `ttl` seconds after the process starts, regardless of startup jitter.

   ### ADR 4: Localhost Binding for Security
   - **Problem:** `-p 5432` exposed the port on all network interfaces.
   - **Decision:** Use `-p 127.0.0.1::5432` to bind only to localhost.
   - **Result:** The database is not accessible from other machines – reduces attack surface.

   ### ADR 5: Volume Cleanup on Removal
   - **Problem:** Anonymous volumes accumulated over time (Postgres image declares a volume).
   - **Decision:** Add `-v` to `docker rm` commands to delete the volume when the container is removed.
   - **Result:** No disk space leaks; volumes are cleaned up immediately.

   ### ADR 6: Centralised Error Handling for Cleanup
   - **Problem:** `cleanup_container` can raise `RuntimeError` in several places; repeated try/except blocks scattered across commands.
   - **Decision:** Introduce `_safe_cleanup` that catches and prints errors, returning `True`/`False`.
   - **Result:** Consistent error handling, reduced duplication, cleaner CLI code.

   ### ADR 7: File‑Based Locking for Concurrency
   - **Problem:** Two `devdb start` processes in the same directory could race.
   - **Decision:** Use `portalocker` to acquire a file lock before starting the container.
   - **Result:** Concurrency is safe; the lock is tested explicitly in CI.

   ---

   ## Concurrency & Race Conditions

   DevDB uses deterministic container names based on the current working directory (`devdb-{hash}`). Multiple projects never conflict.

   **Within the same directory**, a file‑based lock (`portalocker`) prevents two `devdb start` processes from interfering. An explicit integration test (`test_concurrent_start_lock`) proves that the lock works.

   ---
   ### Failure Handling

   | Scenario | How DevDB Handles It |
   | :--- | :--- |
   | **Docker not running** | `docker info` fails; `cli.py` catches `RuntimeError` and prints a clear error with a suggestion to start Docker. |
   | **Postgres fails to become ready** | Health check times out after 30 seconds; `cleanup_container()` is called; tool exits with error. |
   | **TTL cleanup fails** | `_safe_cleanup` catches `RuntimeError`, prints the error, and returns `False`; the command exits with code 1. |
   | **Ctrl+C during startup** | `KeyboardInterrupt` is caught; `_safe_cleanup()` is called to remove the container. |
   | **Process exits unexpectedly** | `atexit` registers a fallback cleanup to remove the container. |
   | **TTL already expired** | `remaining` is negative; `time.sleep` is skipped and cleanup runs immediately. |
   | **Negative remaining guard** | time.sleep is skipped when TTL already expired. |

   ### Cross-Platform Support

   The tool uses `subprocess` with list arguments (no `shell=True`), `pathlib` for file paths, and avoids system‑specific dependencies. It works on Linux, macOS, and Windows (with Docker Desktop). Signal handling for `SIGINT` is the only area where behaviour may vary slightly, but the fallback `atexit` cleanup ensures reliability.

   ---

   ## Testing Strategy

   We have three layers of tests:

   - **Unit tests** (`tests/unit/`): Fast, no Docker. They test the config loader, random string generator, port finder, and container naming logic.
   - **Integration tests** (`tests/integration/`): Slower, use real Docker. They spin up a container, connect to it, run a query, and verify cleanup works via both Ctrl+C and TTL expiry. These tests use retry loops instead of hardcoded sleeps, so they are not flaky.
   - **Error path tests** (`tests/integration/test_errors.py`): Mock `subprocess.run` to simulate Docker being unavailable, ensuring the tool fails gracefully.
   - **Complex integration tests** (`tests/integration/real_test_usage_test.py`): Simulate real-world workflows: Alembic migrations, `pytest` integration, schema + seed + test pipelines, and failure recovery with container cleanup.

   The integration tests run in isolated temporary directories, so they never interfere with each other. Each test gets its own deterministic container name, preventing cross-test contamination.

   ---

   ## Current Status

   | Feature | Status |
   | :--- | :--- |
   | `devdb start` – spins up Postgres | ✅ Complete |
   | `devdb stop` – stops and removes container | ✅ Complete |
   | `devdb status` – shows container state (port, TTL, etc.) | ✅ Complete |
   | `devdb init` – config generator | ✅ Complete |
   | `devdb seed` – SQL/CSV loading | ✅ Complete |
   | `devdb test` – ephemeral DB for commands | ✅ Complete |
   | Dynamic port allocation (localhost only) | ✅ Complete |
   | Absolute TTL with auto‑cleanup | ✅ Complete |
   | Ctrl+C graceful shutdown | ✅ Complete |
   | Idempotent cleanup | ✅ Complete |
   | Volume cleanup (`-v` flag) | ✅ Complete |
   | Concurrent start protection (`portalocker`) | ✅ Complete |
   | Unit & Integration tests | ✅ Complete |
   | CI Pipeline (GitHub Actions) | ✅ Complete |
   | PyPI `v0.2.0` | ✅ Complete |


   ---

   ## Project Structure

   I use a `src/` layout to prevent import issues when running tests.

   ```
   devdb/
   ├── src/
   │ └── devdb/
   │       ├── __init__.py
   │       ├── cli.py
   │       ├── container.py
   │       └── config.py
   ├── tests/
   │   ├── unit/
   │   │    ├── config_test.py
   │   │    └── container_utils_test.py
   |   |    └── container_helper_test.py
   │   └── integration/
   │       ├── start_test.py
   │       └── errors_test.py
   │       └── init_test.py
   │       └── seed_test.py
   |       ├── test_test.py
   |       └── real_test_usage_test.py
   |       └─ lifecycle_test.py
   ├── docs/
   │ └── ARCHITECTURE.md
   ├── pyproject.toml
   ├── .pre-commit-config.yaml
   ├── .gitignore
   └── README.md
   ```

   ---

   ## Why This Architecture?

   Optimized for three things:

   1. **Reliability** – no flaky tests, no orphaned containers, no race conditions.
   2. **Simplicity** – minimal dependencies, straightforward code, easy to debug.
   3. **Developer experience** – clear output, intuitive commands, a tool that just works.

   No ORM, no async, no microservices. Just a CLI tool that orchestrates Docker and gives you a Postgres database on demand.

   *Last updated: 6 September 2026*