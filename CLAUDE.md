# ElixirX Sales Portal — Codebase Notes

Project context for AI assistants. The README is for human onboarding; this
file captures architectural conventions, domain rules, and current state that
aren't obvious from reading the code.

## Project Overview

ElixirX Sales Portal — full-stack web app for Core Pacific Inc.

- **Frontend:** React + TypeScript + Vite + Tailwind CSS (in `/frontend`)
- **Backend:** Python + FastAPI (in `/backend`)
- **Database:** Supabase PostgreSQL
- **Dev tool:** Claude Code in VS Code with the `elixirx-dev` MCP server (in `/mcp_server`)
- **Repo:** https://github.com/h13062/elixirx-portal

## Test Accounts

- **Super Admin:** `bgh.huybui@gmail.com` / `Huy13062` (role: `super_admin`)
- **Admin:** `bgh1506@gmail.com` / `Huy13062` (role: `admin`)
- **Rep:** `minh.tran@example.com` / `Minh2026!` (role: `rep`, tier: `agent`)
- **Admin bootstrap code:** `Core4008$` (one-time use for first super-admin setup)

## Architecture

- **Frontend:** Pages in `frontend/src/pages/`, feature components in `frontend/src/components/<feature>/`, shared utilities in `frontend/src/lib/` (auth, api client, downloads).
- **Backend:** Thin **router → service → repository → Supabase** layering. All business logic lives in services; routers are HTTP-only adapters; repositories own table access.
  - `backend/app/routers/` — FastAPI route handlers
  - `backend/app/services/` — business logic
  - `backend/app/repositories/` — Supabase table access (one class per table)
  - `backend/app/models/` — Pydantic request/response models
  - `backend/app/core/` — auth, Supabase clients, helpers, notification helper, config
- **Two Supabase clients:** `supabase` (user-context) and `supabase_admin` (service-role). All backend reads/writes use `supabase_admin`. See [docs/bug-log/sprint-1.md](docs/bug-log/sprint-1.md) Bug 1.8 — sharing a single client between user and admin operations causes auth contamination.

## Sprint Status

| Sprint | Focus | Status |
|--------|-------|--------|
| 0  | Project Setup | ✅ Complete |
| 1  | Authentication | ✅ Complete |
| 2  | Inventory & Batch Tracking | ✅ Complete |
| 3  | Machine Lifecycle & Warranty | ✅ Complete |
| 4  | Dashboard & Notifications | 🔄 In Progress (4.0–4.2 done) |
| 5  | Leads & Customers | ⏳ Pending |
| 6  | Orders | ⏳ Pending |
| 7  | Commissions | ⏳ Pending |
| 8  | Tickets | ⏳ Pending |
| 9  | User Management & Settings | ⏳ Pending |
| 10 | Email & Polish | ⏳ Pending |
| 11 | Deployment | ⏳ Pending |

## Sprint 3 Task Breakdown

| Task | What | Status |
|------|------|--------|
| 3.0 | Database migration (machine_status_log, warranty, reservations, notifications, machine_issues) | ✅ Done |
| 3.1 | Backend: machine status transitions with logging | ✅ Done |
| 3.2 | Backend: warranty endpoints (set, extend, check expiring, PDF certificate) | ✅ Done |
| 3.3 | Backend: reservation endpoints (request, approve, deny, expire) | ✅ Done |
| 3.4 | Backend: machine issues endpoints (report, track, resolve) | ✅ Done |
| 3.5 | Backend: notification endpoints (create, list, mark read, broadcast) | ✅ Done |
| 3.6 | Frontend: inventory tabs + machine detail page | ✅ Done |
| 3.7 | Frontend: admin machine actions UI | ✅ Done |
| 3.8 | Frontend: warranty page UI | ✅ Done |
| 3.9 | Frontend: reservation UI + by-account analytics + sortable table + rep filter | ✅ Done |

## Sprint 4 Task Breakdown

| Task | What | Status |
|------|------|--------|
| 4.0 | Dashboard layout + summary endpoint (`GET /api/dashboard/summary`) | ✅ Done |
| 4.1 | Warranty expiration alerts widget (extend + certificate actions) | ✅ Done |
| 4.2 | Low stock alerts widget (mini cards, progress bar, OUT OF STOCK badge) | ✅ Done |
| 4.3 | Activity feed | ⏳ Pending |
| 4.4 | Issue tracker widget | ⏳ Pending |
| 4.5 | Notification bell | ⏳ Pending |
| 4.6 | Summary reports | ⏳ Pending |
| 4.7 | Role-based views | ⏳ Pending |
| 4.8 | Sprint 4 full test pass | ⏳ Pending |

> Note: data for the 4.3 activity feed and 4.4 issues widget already ships in
> `/api/dashboard/summary` (`recent_activity`, `recent_issues`). The pending
> tasks are the dedicated UI / interaction layers.

## Key Architecture Decisions

- **[DECISION]** `handle_new_user` Supabase trigger DISABLED — profile creation handled in Python after `supabase.auth.admin.create_user()` returns (sprint-1 Bug 1.6).
- **[DECISION]** RLS disabled on most tables — backend uses `service_role` key and enforces access control in code (sprint-1 Bug 1.7).
- **[DECISION]** Two Supabase clients: `supabase` (user-context) and `supabase_admin` (service role) — prevents auth-state contamination on `auth.admin.*` calls (sprint-1 Bug 1.8).
- **[DECISION]** Never use `.single()` — always `.execute()` and check `result.data` (sprint-1 Bug 1.5).
- **[DECISION]** Admin creates rep accounts directly with auto-generated passwords (Supabase free-tier email is unreliable) (sprint-1 Bug 1.9).
- **[DECISION]** Each supplement flavor has its own SKU (`SUPP-FA` … `SUPP-FE`).
- **[DECISION]** Consumable batches tracked with full manufacturing traceability (`manufacture_date`, `expiry_date`, `shipped_date`, `shipped_to`); `consumable_stock.quantity` is a derived `SUM(batches.quantity)` aggregate, not a source of truth (sprint-2 Bug 2.5).
- **[DECISION]** Friendly identifiers everywhere — routes accept UUID **or** SKU/serial/name; resolution lives in `find_by_identifier` on each repository (sprint-2 Bugs 2.1–2.3).
- **[DECISION]** Static FastAPI routes registered before dynamic ones, both within and across routers (sprint-2 Bug 2.8, sprint-3 Bug 3.9).
- **[DECISION]** Full CRUD per resource — no Create+Read with deferred Update/Delete (sprint-2 Bugs 2.6, 2.7).
- **[DECISION]** Sprint order changed: Machine Lifecycle (3) and Dashboard (4) prioritized before Leads/Customers/Orders.
- **[DECISION]** `elixirx-dev` MCP server added for development automation (database queries, test runs, project introspection, migration helpers).

## Database Tables

15 tables in `public` schema (verified live via MCP `list_tables`):

| Sprint | Table | Purpose |
|--------|-------|---------|
| 1 | `profiles` | User profile (role, tier, full_name) |
| 1 | `invitations` | Rep invite tokens |
| 1 | `admin_codes` | One-time admin bootstrap codes |
| 1 | `admin_log` | Admin action audit log |
| 1 | `system_config` | Key/value runtime config |
| 2 | `products` | Catalog (machines + consumables) |
| 2 | `machines` | Serialized machine inventory |
| 2 | `consumable_stock` | Per-product aggregate (derived from batches) |
| 2 | `supplement_flavors` | Flavor variants for SUPP-PACK |
| 2 | `consumable_batches` | Batch-level manufacturing/shipment records |
| 3 | `machine_status_log` | Every status transition (audit invariant) |
| 3 | `warranty` | Customer warranty records (set/extend) |
| 3 | `reservations` | Rep reservation workflow |
| 3 | `notifications` | In-app notifications |
| 3 | `machine_issues` | Issue reports + resolution |

## Backend Routers

8 routers under `backend/app/routers/`. Registered in [`backend/app/main.py`](backend/app/main.py) — `machine_lifecycle` MUST be included before `inventory_router` so static `/machines/status-summary` and `/machines/bulk-status` paths resolve before `/machines/{machine_id}` catches them (sprint-3 Bug 3.9).

| Router | Endpoints |
|--------|-----------|
| `auth_router` | `/api/auth/login`, `/logout`, `/me`, `/admin-setup`, `/admin-codes/*`, `/admin-log`, `/invite`, `/invitations`, `/change-password` |
| `inventory_router` | `/api/products`, `/machines`, `/consumable-stock`, `/consumable-batches`, `/supplement-flavors` (full CRUD on each) |
| `machine_lifecycle` | `/api/machines/status-summary`, `/bulk-status`, `/{id}/status`, `/{id}/status-history`, `/{id}/full-detail`, `DELETE /machines/{id}` |
| `warranty` | `/api/warranty` (CRUD), `/dashboard`, `/check-expiring`, `/machine/{id}`, `/certificate/{id}` (PDF), `/{id}/extend` |
| `reservations` | `/api/reservations` (request/approve/deny/cancel/expire) + by-account analytics |
| `issues` | `/api/issues` (CRUD + status), `/summary`, `/machine/{id}` |
| `notifications` | `/api/notifications` (list/read/clear), `/unread-count`, `/read-all`, `/broadcast` |
| `dashboard` | `/api/dashboard/summary` (Sprint 4 — aggregates all sections in one round trip) |

## Frontend Pages

14 pages under `frontend/src/pages/`:

| Page | Purpose |
|------|---------|
| `Login.tsx` | Email + password login |
| `AdminSetup.tsx` | One-time super-admin bootstrap |
| `Dashboard.tsx` | Sprint 4 dashboard (summary cards, alerts, activity feed) |
| `Inventory.tsx` | Three-tab inventory (Machines / Filters / Consumables) |
| `MachineDetail.tsx` | Full lifecycle view: status, warranty, reservations, issues |
| `Warranty.tsx` | Warranty list + dashboard tab |
| `Issues.tsx` | Issue tracker |
| `UserManagement.tsx` | Admin: rep invite + management |
| `SettingsPage.tsx` | User profile + system config |
| `Leads.tsx` | Sprint 5 stub |
| `Customers.tsx` | Sprint 5 stub |
| `Orders.tsx` | Sprint 6 stub |
| `Commissions.tsx` | Sprint 7 stub |
| `Tickets.tsx` | Sprint 8 stub |

## Core Conventions

- **Never use `.single()`.** Always `.execute()` and check `result.data[0]`.
- **Friendly identifiers everywhere.** Route handlers go through `find_by_identifier`; raw UUIDs are internal-only.
- **Static FastAPI routes before dynamic ones** — both within and across routers.
- **Full CRUD per resource.** Don't ship Create+Read and defer Update/Delete.
- **Bug log first.** Every non-trivial bug goes in [docs/bug-log/](docs/bug-log/) — check there before debugging unfamiliar errors.

## Inventory Domain

### Stock model — derived aggregate

`consumable_stock.quantity` is **not** a source of truth. It is recalculated as `SUM(consumable_batches.quantity)` after every batch insert/update/delete/ship via `InventoryService._recalculate_stock(product_id)`. Editing it directly bypasses the invariant.

### Supplement Pack — flavored consumable

The supplement product has variants tracked in `supplement_flavors`. Batches for the supplement pack **must** carry a `flavor_id`; batches for any other consumable **must not**. See `InventoryService.create_batch` validation.

## Machine Lifecycle (Sprint 3)

### Status state machine

`machines.status` is a `machine_status` enum with values: `available`, `reserved`, `ordered`, `sold`, `delivered`, `returned`.

Forward transitions allowed:

| from        | to                       |
|-------------|--------------------------|
| available   | reserved                 |
| reserved    | available, ordered       |
| ordered     | sold, available          |
| sold        | delivered, available     |
| delivered   | returned                 |
| returned    | available                |

Defined in [`backend/app/services/machine_lifecycle_service.py`](backend/app/services/machine_lifecycle_service.py) as `VALID_TRANSITIONS`.

### Audit log invariant

**Every** machine status change writes a row to `machine_status_log` with `(machine_id, from_status, to_status, changed_by, reason, created_at)`. There are no exceptions — bulk updates log each transition individually. The log is the only system of record for who moved a machine between states and why.

### Force override

Admin requests to `PUT /api/machines/{identifier}/status` may include `force=true` in the body. This skips the `VALID_TRANSITIONS` check and still writes a log entry, but the `reason` is automatically prefixed with `FORCED:` so audits can identify out-of-band moves. Use only when correcting bad data.

## Dashboard (Sprint 4)

`GET /api/dashboard/summary` aggregates everything in one round trip — no per-section endpoints. Sub-section failures are best-effort: a single missing table returns its zero/empty default and the rest of the response still loads.

Sections:
- `machines` — counts grouped by status
- `warranties` — active / expiring_soon / expired / total
- `issues` — counts by status + urgent/high breakdown (filtered to caller for reps)
- `reservations` — counts by status (filtered to caller for reps)
- `low_stock` — items below `min_threshold` + `total_tracked` (Task 4.2)
- `recent_activity` — last 10 `machine_status_log` entries with rep name
- `recent_issues` — top 5 open/in_progress issues sorted by priority then recency
- `expiring_warranties` — warranties expiring within 30 days
- `expired_warranties` — warranties already past `end_date`

## Testing

- **Total tests:** 138 (sprint1: 12, sprint2: 30, sprint3: 88, sprint4: 10).
- **Test files (8):** `test_auth.py`, `test_dashboard.py`, `test_inventory.py`, `test_issues.py`, `test_machine_lifecycle.py`, `test_notifications.py`, `test_reservations.py`, `test_warranty.py`.
- Test credentials live in [`backend/tests/conftest.py`](backend/tests/conftest.py) — three sessions: super_admin, admin, rep.
- Test data uses `TEST-` / `RX-` / `LOT-` / `SKU-` prefix (with random suffix via `unique_id()`) for easy identification and cleanup.
- pytest config at [`backend/pytest.ini`](backend/pytest.ini) sets `pythonpath = . tests` so `from conftest import unique_id` resolves.
- ALWAYS run tests before `git push`.

### Markers (declared in `backend/pytest.ini`)

- **Sprint level:** `sprint1`, `sprint2`, `sprint3`, `sprint4`
- **Task level:** `sprint3_1` … `sprint3_9`, `sprint4_0` … `sprint4_8`
- Test files declare `pytestmark = pytest.mark.sprintN` at module level so every test inherits the sprint tag without per-method decoration.
- Per-method `@pytest.mark.sprintN_M` adds the task-level tag on top.
- **Workflow:** task-level (`-m sprint4_2`) during development, sprint-level (`-m sprint4`) before push, all tests before merge.

### Test commands

| Command | What |
|---------|------|
| `pytest tests/ -v --tb=short` | Run all tests |
| `pytest tests/ -v -m sprint4` | Run a sprint |
| `pytest tests/ -v -m sprint4_2` | Run a single task |
| `pytest tests/test_dashboard.py -v` | Run a file |
| `pytest tests/test_dashboard.py::TestLowStockAlerts::test_dashboard_low_stock_structure -v` | Run one test |
| `pytest tests/ -v -x` | Stop on first failure |
| `.\run_tests.ps1` / `.\run_tests.ps1 -Sprint 3` | PowerShell runner |
| `run_tests.bat` / `run_tests.bat 3` | CMD runner |

## MCP Server (`elixirx-dev`)

Local MCP server in [`/mcp_server/`](mcp_server/) that exposes development-automation tools to Claude Code. Stdio transport; loads env from `backend/.env` automatically.

### Tools (15 total, in 4 modules)

**`tools/database.py`** — Supabase access (uses `service_role` key)
- `query_table(table, columns, filters, limit, order_by)` — PostgREST select
- `list_tables()` — schema introspection (probes known tables for row counts + columns)
- `check_table_exists(table_name)` — boolean existence probe
- `count_rows(table, filters)` — row count, optionally filtered
- `run_sql(query)` — read-only SELECT (requires `exec_sql` RPC; not available on this project)

**`tools/testing.py`** — pytest runner
- `run_tests(marker, test_file, test_name, stop_on_first_failure, verbose)` — invoke pytest with optional filters; 300s timeout
- `list_test_markers()` — read `pytest.ini` and return registered markers
- `get_test_summary()` — run each sprint marker and report pass/fail tail

**`tools/project.py`** — file/code introspection
- `read_file(file_path)` — read project file (truncates at 10k chars)
- `list_project_files(directory, pattern)` — list files, skipping noisy dirs
- `search_code(...)` — code search
- `get_project_status()` — sprint info from CLAUDE.md plus file counts

**`tools/migration.py`** — schema operations
- `run_migration(sql, description)` — apply SQL migration
- `generate_migration(...)` — generate migration template
- `check_migration_status()` — list current schema state

### How to connect

The MCP server runs over stdio; configure Claude Code to launch `python mcp_server/server.py` with `PROJECT_ROOT` pointing at the repo root. The server reads `backend/.env` for Supabase credentials.

> Note: when bumping the timeout in `mcp_server/tools/testing.py`, the running MCP server must be restarted for the new value to take effect. The harness loads the constant once at startup.

## Daily Dev Commands

```powershell
# Start backend (Windows / PowerShell)
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Start frontend
cd frontend
npm run dev

# Run all tests
cd backend
pytest tests/ -v --tb=short

# Run by sprint / task
pytest tests/ -v -m sprint3
pytest tests/ -v -m sprint4_2

# Git
git add .
git commit -m "message"
git push
```

## Documentation

- [docs/bug-log/](docs/bug-log/) — every notable bug with symptom, root cause, fix, prevention. Indexed by sprint.
- [docs/bug-log/README.md](docs/bug-log/README.md) — common patterns checklist; consult before debugging.
