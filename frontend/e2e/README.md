# B10 · Staff browser acceptance

The five default journeys create no business records. Login, session activity, throttling and logout are real. A sixth, opt-in journey writes a booking and a synthetic payment in a **separate, disposable database**. A separately selectable keyboard walkthrough uses its own fresh database. Each test gets a new Chromium context; there is no shared or saved authentication state.

## Operator setup

1. Start the migrated application and serve the UI **and** `/api/v1/` from one origin (Vite dev proxy or the published Compose frontend port). Set `E2E_BASE_URL` to that frontend origin, e.g. `http://127.0.0.1:5187` for the default Vite server. Only HTTP(S) on `127.0.0.1`, `localhost` or `[::1]` is accepted. Don't point the suite at Django alone.
2. Set `HMS_DEMO_USER` and `HMS_DEMO_PASSWORD` privately in the runner environment. The account must have `dashboard.view`, `guests.view`, `rooms.view` and `reservations.view` (e.g. a demo Receptionist). The credentials are not passed on the CLI. Missing setup is a failure, not a skipped test.
3. Keep fixtures stable during a run. At least one synthetic **guest** is required to demonstrate data → failure → empty → restored data on the same screen. The development `seed_demo` catalog supplies a guest and rooms. To cover populated reservation rows as well, prepare a synthetic reservation before running; bookings need not have fixed dates or IDs. Never seed or alter a live database for these checks.
4. With dependencies installed, run from `frontend/`. Leave `PLAYWRIGHT_CHANNEL` unset for Playwright's bundled Chromium:

   ```sh
   npx playwright install chromium  # once, if the matching browser is not installed
   npm run e2e
   ```

   Alternatively, to use **installed Microsoft Edge** on Windows, skip the browser download and run in PowerShell:

   ```powershell
   $env:E2E_BASE_URL = 'http://127.0.0.1:5187'
   $env:PLAYWRIGHT_CHANNEL = 'msedge'
   npm run e2e
   ```

   Both channels use the `chromium` project. The test harness can be type-checked with `npx tsc -p e2e/tsconfig.json`. To check discovery only: `npx playwright test --config=e2e/playwright.config.ts --list` (set `E2E_BASE_URL` first). Neither is browser evidence.

**Write journey and restore:** From the repository root, after local setup, run `.\.venv\Scripts\python.exe scripts/rehearse_browser.py` (POSIX: `.venv/bin/python scripts/rehearse_browser.py`). Set `PLAYWRIGHT_CHANNEL=msedge` for installed Edge on Windows. This runner creates a new database, media directory, staff login and front/back servers on ports 5189/8019. It alone sets `HMS_E2E_DISPOSABLE=1`; do not set that flag for an existing workspace. Following browser success it stops both servers, restores the database archive and media in isolation, compares the results and removes the scratch resources. Local `pg_dump` and `pg_restore` matching the server are required on `PATH` or in `PG_BIN`.

**Narrow keyboard walkthrough:** run the same `scripts/rehearse_browser.py` command with `--keyboard-only`. The runner sets both opt-ins and selects only `keyboard.spec.ts`. From a clean initial fixture it uses 360 CSS px and real Tab/Enter/Space input to find and confirm a prepared booking, handle an unpaid-checkout refusal, review a counted synthetic cash voucher and finish an assigned cleaning task. It checks focus indication and overflow on those surfaces; it is not a full accessibility audit.

## Fixture → action → required observation

| Case | Fixture and action | Pass requires |
| --- | --- | --- |
| Anonymous / invalid login | Fresh context opens `/reservations`; one generated unregistered identity submits the sign-in form. | `auth/me` is anonymous; login controls instead of reservation UI; the same cookie jar gets a JSON 401/403, not a list. A real credential rejection leaves an alert and no session, even on a new deep link. |
| Staff session / overview | Valid front-desk staff signs in by keyboard, reloads the overview and selects *Arriving today*. | Identity and roles survive reload; four separately labelled counts and the property date match the browser's actual dashboard response. Arrival/departure counts must be labelled scheduled, not recorded. Guest profile total also matches the scoped guest catalog count. Board IDs/empty notice reflect the selected subset of the briefing. |
| Catalog navigation | Staff follows the visible Guests, Rooms and Reservations links. | Relevant route, active link and heading; a real 200 page with a consistent count. Nonempty pages have the expected number of records and a matching guest reference/name, room category/capacity/condition, or booking ID/guest/dates/status. A truly empty catalog has its own notice, not a failed fetch. |
| Error vs. empty vs. restored data | Submit a unique search in the populated guest directory. Disconnect **only that GET, once**, in Chromium; press Retry, then Clear. | An alert with Retry, no stale table and no empty message on failure. Retry goes to the real API for the identical search (`200`, zero results); the UI now explicitly says no matches. Clear issues an unfiltered read and restores the count and original first-page identities. No successful response, login or authorization denial is mocked. |
| Mobile session boundary | At 390×844, tap the drawer, follow Rooms, reopen the drawer and sign out. Try Back and a direct protected visit. | Navigation opens and closes, live room catalog fits the page width, and server accepts logout. The formerly successful room endpoint now denies this context. Back cannot restore the workspace, and a fresh boot returns `user:null`. |
| Opt-in stay | Book a named synthetic room, check in, attempt unpaid checkout, record a counted test voucher, then check out. | Refusal leaves occupancy and folio intact with no task; payment produces one receipt; departure closes the zero-balance folio, releases occupancy and creates exactly one dirty-room turnover task. Scoped GETs check the UI against persisted state. |

The test config uses one worker, no retries, and no traces, screenshots, video or retained failure output. Do not enable request/credential debugging or publish raw browser artifacts. Record redacted test names, pass/fail counts, target stack/revision and fixture state in the integration report. A run with an empty reservation directory is evidence for the **empty** branch only. These UI checks do not replace PostgreSQL integrity, API role-matrix or component tests.
