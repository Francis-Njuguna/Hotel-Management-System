# Verification

Use a disposable PostgreSQL database with permission to create a test DB and enable `btree_gist`. `pytest-django` creates an isolated `test_…` database. In particular, do not substitute SQLite for booking or parking contention tests.

| Layer | Acceptance evidence |
|---|---|
| DB and Django services | Date/exclusion constraints and the lock ordering that protects admission, service posting, checkout and settlement. Check affected rows from an independent connection, including rollback on a conflict. |
| REST / RBAC | Positive and denied operations for the seven roles; compare list, detail, media and aggregate scopes. Test CSRF on login/writes, logout and password recovery. For refused requests assert no business mutation. |
| Financial | Exact decimals, one payment/receipt per tender reference, one charge per billable source, no overpayment, checkout refuses outstanding balance, distinct charges versus receipts. |
| Frontend components | Loading/empty/error states, permission visibility, date and money entry, accessible labels, and behavior after a server rejection. |
| Real browser | Exercise the real local session/API, desktop and phone layouts, and staff navigation. Only the error/retry case deliberately disconnects a single GET; no successful API response is mocked. Supply local demo credentials privately, or use the isolated runner below. |
| Recovery | `scripts/verify_restore.py` restores a PostgreSQL archive and private demo media in isolation. It compares counts, amounts, the extension, hashes over complete claim and receipt rows, and media paths and hashes. The [Compose drill](../../deploy/rehearse.py) additionally checks the restored receipt and role-specific image access over HTTP. |

Commands: from `backend/`, run `../.venv/Scripts/python.exe -m pytest -q` (POSIX `../.venv/bin/python -m pytest -q`); from `frontend/`, `npm run build`, `npm test`, `npm run e2e`. The tracker records actually executed checks separately from this strategy.

For the six browser journeys **and the populated recovery rehearsal**, run `scripts/rehearse_browser.py` with the project's virtual environment from the repository root. Run it separately with `--keyboard-only` for the 360 CSS px walkthrough and its matched restore. Each invocation uses a fresh database. See the [browser instructions](../../frontend/e2e/README.md) for browser binaries and prerequisites and the [API traceability matrix](../../backend/tests/README.md) for the two-connection contention and rollback tests.

Run `python -I -S -B -m unittest discover -s scripts -p test_demo_config.py -v` from the root to check native/Docker demo isolation with temporary files and mocked process/network boundaries. These tests verify rejected targets cannot start a migration, seed, proxy or database process.

For a reproducible, single-client HTTP timing sample, run `python -m pytest -qs benchmarks/workload.py` from `backend/` in the same PostgreSQL test environment. It initializes 60 rooms, 600 guests and 1,200 dated bookings in a new test database, checks both availability pages and dashboard figures, then reports median and nearest-rank p95 over 30 reads of each endpoint following warm-up. It is an opt-in measurement, independent of the functional suite.
