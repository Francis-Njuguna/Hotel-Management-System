# Hotel A · Hotel Management System

A staff workspace for reception, housekeeping, maintenance, restaurant, billing, parking and hotel management. It runs as a React/TypeScript application backed by Django REST Framework and PostgreSQL. Hotel A is an anonymized property; the optional demo uses synthetic data.

## Run the local demo

**Windows:** install Python 3.12, Node.js 22.12+ with npm, and PostgreSQL 18 with its command-line tools (or Docker Desktop). Double-click **`Start Hotel A.cmd`** in the checkout. From a terminal the equivalent command is:

```powershell
py -3.12 scripts/run_local.py
```

Open **<http://127.0.0.1:5187>**. The launcher installs dependencies, starts a separate local database, applies migrations and creates a synthetic catalog. On first run, it writes a random local administrator login to **`.local/demo-credentials.txt`**. Keep this file private. The native Windows setup uses port `55488` and does not modify the installed PostgreSQL service. Set `PG_BIN` if the PostgreSQL executables are not in the standard location. If the launcher reports a conflicting setting, use a clean terminal without deployment `POSTGRES_*` or `HMS_*` variables. It preserves an existing `.env` on mismatch.

**Linux/macOS with Docker:** install the same Python/Node versions and run `python3 scripts/run_local.py` from the repository root. The local database helper binds a dedicated PostgreSQL container to loopback. For the containerized application, see the [Compose deployment and recovery guide](docs/technical/deployment_guide.md).

## Try the guest-to-checkout workflow

1. Register a guest and reserve one or more rooms for the same dates. A confirmed booking or a blocking repair prevents a second sale of the same room-night.
2. Check in the confirmed reservation on an eligible day. All named rooms must be vacant, active and inspected. The folio opens at the rates agreed when booking.
3. Submit a room-service order for a room on the stay, then advance it to **served**. Its items appear on the folio once. Dine-in orders have separate invoices.
4. Record a tender only after funds have been received or independently verified. The system issues a receipt and keeps **KES billed** separate from **KES collected**. No payment gateway is connected. Use synthetic transactions only in the demo.
5. Check out after settling the balance and finishing open orders. Assign the resulting cleaning task, complete it, then inspect the room before admitting the next guest.

The remaining screens cover room catalogs/photos, guest and reservation history, maintenance closures, menu/pricing, parking assignments and releases, staff access, notifications and audit activity. The dashboard reads the same records and filters its contents for the signed-in role.

## Verification and project files

| Resource | What it contains |
|---|---|
| [Project status](PROJECT_STATUS.md) | Verification evidence, review decisions and outstanding work |
| [Staff guide](docs/technical/implementation_guide.md) | Workflow walkthrough and module map |
| [Testing](docs/technical/testing_strategy.md) | PostgreSQL race tests, API and browser checks, restore rehearsal |
| [Requirements](docs/requirements/srs.md) | Nine modules, seven roles and measurable acceptance cases |
| [System design](docs/system-design/system_design.md) · [database](docs/system-design/database_design.md) · [ERD](docs/diagrams/erd.mmd) | API and database boundaries, financial rules and locking |
| [Deployment](docs/technical/deployment_guide.md) | Same-origin installation, service configuration, backups and recovery |

The academic context is **Chuka University, ACSC 483 — Software Project 1**. The [discovery report](docs/discovery_report.md) and [blank research instruments](docs/research/investigation_plan.md) are separate from the software. They do not establish findings or approvals for Hotel A.
