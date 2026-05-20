# ElixirX Sales Portal

A full-stack sales operations platform for Core Pacific Inc.'s ElixirX hydrogen water product line. Built with React, FastAPI, and Supabase.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | Python + FastAPI |
| Database | Supabase (PostgreSQL + Auth) |
| Testing | pytest with sprint/task-level markers |
| Dev Tools | MCP Server (`elixirx-dev`) + Development Agent (watch / review / fix) |
| Version Control | Git + GitHub |

## Features

### Sprint 1 — Authentication ✅
- Role-based access (Super Admin, Admin, Sales Rep with 3 tiers — Distributor 10%, Agent 10–20%, Master Agent 25%)
- Admin creates rep accounts with auto-generated passwords (Supabase free-tier email is unreliable)
- JWT session management with frontend auto-refresh on 401
- Protected routes with role-based sidebar navigation

### Sprint 2 — Inventory & Batch Tracking ✅
- Machine registration with serial number tracking (RX Machine $5,995 / RO Machine $3,995)
- Consumable stock with batch-level manufacturing traceability (manufacture / expiry / shipped dates)
- Supplement flavor management with individual SKUs (`SUPP-FA` … `SUPP-FE`)
- Full CRUD for products, flavors, machines, and batches
- Friendly identifier lookup — UUID, SKU, serial, or name accepted on every endpoint
- Low stock detection with configurable per-product thresholds

### Sprint 3 — Machine Lifecycle & Warranty ✅
- Status transitions: `available → reserved → ordered → sold → delivered → returned`
- Audit trail: every change writes to `machine_status_log` with who/when/why; admin force override prefixes the reason with `FORCED:`
- Warranty tracking: create, extend, PDF certificate generation (fpdf2), expiring/expired dashboard
- Reservation workflow: rep requests → admin approves/denies → 7-day countdown → auto-expiry; by-account analytics with rep filter
- Machine issue tracking with priority (Low / Medium / High / Urgent) and resolution notes
- In-app notification system with `notify_admins` / `notify_user` helpers wired into status / reservation / warranty / issue events

### Sprint 4 — Dashboard & Notifications ✅
- Single-endpoint dashboard (`GET /api/dashboard/summary`) — 9 sections in one round trip
- Warranty expiration alerts widget — inline extend + PDF certificate download
- Low stock alerts widget — mini cards with progress bar, OUT OF STOCK badge, pulsing critical indicator
- Machine status activity feed — vertical timeline with colored status dots, type badges, fade-in animations, fresh-entry glow
- Issue tracker widget — priority-sorted cards with Start / Resolve quick actions (admin), pulsing urgent indicator
- Notification bell — red badge with pulse on new arrivals, 30 s poll of unread count, click-to-mark-read with smart navigation, full `/notifications` page with filter tabs and bulk actions
- Daily / weekly summary report — 3×3 stat grid: machines registered/delivered, status changes, warranties created, reservations, issues, batches, shipments, top rep
- Role-based views — admin sees the operational dashboard; rep sees personal "my reservations" / "my issues" lists, three personal summary cards, and rep-focused quick actions
- Dedicated `GET /api/activity` endpoint backing a future paginated activity page

## Development Agent

Built-in development automation living at [`mcp_server/agent/`](mcp_server/agent/):

| Mode | Command | What it does |
|------|---------|-------------|
| **Watch** | `.\mcp_server\agent\watch.ps1` | Auto-runs **task-level** tests on file save (1.5 s debounce); `.ts/.tsx` saves trigger `npx tsc --noEmit` |
| **Review** | `.\mcp_server\agent\review.ps1` | Pre-push checks: full pytest, debug-artifact scan, `.env` exposure, hardcoded-secret scan, router/test coverage diff |
| **Fix** | *"Use elixirx-dev to diagnose the last test failure"* | Pattern-matches the latest watcher failure in Claude Code |
| **Auto-fix** | *"Use elixirx-dev to auto-fix the failing tests"* | Turns the diagnosis into a step plan |
| **Query** | *"Use elixirx-dev to query the products table"* | Direct Supabase read access from Claude Code |

The watcher resolves a changed file to the most specific pytest marker available — `routers/warranty.py` triggers `pytest -m sprint3_2` (only warranty tests), not the whole sprint. Saving a `test_*.py` file runs only that file.

## Project Structure

```
elixirx-portal/
├── frontend/                       # React + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── pages/                  # 15 route-level views
│   │   │   ├── AdminSetup.tsx      # One-time super-admin bootstrap
│   │   │   ├── Commissions.tsx     # Sprint 7 stub
│   │   │   ├── Customers.tsx       # Sprint 5 stub
│   │   │   ├── Dashboard.tsx       # Sprint 4 — full operational dashboard
│   │   │   ├── Inventory.tsx       # Three-tab Inventory (machines / filters / consumables)
│   │   │   ├── Issues.tsx          # Issue tracker
│   │   │   ├── Leads.tsx           # Sprint 5 stub
│   │   │   ├── Login.tsx           # Email + password login
│   │   │   ├── MachineDetail.tsx   # Full machine lifecycle view
│   │   │   ├── Notifications.tsx   # Sprint 4 — full notifications page
│   │   │   ├── Orders.tsx          # Sprint 6 stub
│   │   │   ├── SettingsPage.tsx    # User profile + system config
│   │   │   ├── Tickets.tsx         # Sprint 8 stub
│   │   │   ├── UserManagement.tsx  # Admin: rep invite + management
│   │   │   └── Warranty.tsx        # Warranty list + dashboard tab
│   │   ├── components/             # Layout, NotificationBell, modals, …
│   │   ├── context/                # Theme + auth context
│   │   ├── lib/                    # api client (with auth refresh), download helpers
│   │   └── main.tsx
│   ├── index.html
│   └── package.json
│
├── backend/                        # FastAPI application
│   ├── app/
│   │   ├── routers/                # 8 routers
│   │   │   ├── auth_router.py            # /api/auth/* — login, invite, admin codes
│   │   │   ├── dashboard.py              # /api/dashboard/summary, /report, /api/activity
│   │   │   ├── inventory_router.py       # /api/products, /machines, /consumable-*
│   │   │   ├── issues.py                 # /api/issues/*
│   │   │   ├── machine_lifecycle.py      # /api/machines/{id}/status, /status-summary
│   │   │   ├── notifications.py          # /api/notifications/*
│   │   │   ├── reservations.py           # /api/reservations/* + analytics
│   │   │   └── warranty.py               # /api/warranty/* + PDF certificates
│   │   ├── services/               # Business logic (machine_lifecycle, inventory, …)
│   │   ├── repositories/           # One class per Supabase table
│   │   ├── models/                 # Pydantic request/response models
│   │   ├── core/                   # Auth, two Supabase clients, helpers, config
│   │   └── main.py                 # App entrypoint + router registration
│   ├── tests/                      # 9 test files, 169 tests, sprint + task markers
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_dashboard.py
│   │   ├── test_inventory.py
│   │   ├── test_issues.py
│   │   ├── test_machine_lifecycle.py
│   │   ├── test_notifications.py
│   │   ├── test_notification_bell.py
│   │   ├── test_reservations.py
│   │   └── test_warranty.py
│   ├── pytest.ini                  # Sprint + task-level markers
│   ├── run_tests.ps1               # PowerShell runner
│   ├── run_tests.bat               # CMD runner
│   └── requirements.txt
│
├── mcp_server/                     # elixirx-dev MCP server + Development Agent
│   ├── server.py                   # FastMCP stdio entrypoint
│   ├── tools/                      # MCP-exposed tools (19 total, 5 modules)
│   │   ├── database.py             # query_table, list_tables, count_rows, run_sql
│   │   ├── testing.py              # run_tests, list_test_markers, get_test_summary
│   │   ├── project.py              # read_file, list_project_files, search_code, get_project_status
│   │   ├── migration.py            # run_migration, generate_migration, check_migration_status
│   │   └── agent_tools.py          # diagnose_failure, auto_fix, pre_push_review, get_last_failure_raw
│   ├── agent/                      # Terminal-side Development Agent
│   │   ├── config.py               # FILE_TO_MARKER map + watch settings
│   │   ├── watcher.py              # Watch Mode — task-level test runner on save
│   │   ├── reviewer.py             # Review Mode — pre-push checks
│   │   ├── fixer.py                # Failure pattern matchers (consumed by MCP tools)
│   │   ├── watch.ps1 / watch.bat   # Windows launchers (activates venv)
│   │   └── review.ps1 / review.bat
│   └── requirements.txt            # mcp, supabase, python-dotenv, watchdog
│
├── docs/
│   └── bug-log/                    # Per-sprint bug log (sprints 0–4)
├── CLAUDE.md                       # Architectural conventions + current sprint state
└── README.md                       # This file
```

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- A Supabase project (free tier works for development)

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Runs at http://localhost:5173.

### Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate           # Windows PowerShell
# source venv/bin/activate      # macOS / Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Runs at http://localhost:8000. Interactive API docs at http://localhost:8000/docs. Health check at http://localhost:8000/api/health.

### MCP Server + Development Agent

```powershell
# The mcp + supabase + dotenv + watchdog deps go into the same backend venv.
cd backend
venv\Scripts\activate
pip install -r ..\mcp_server\requirements.txt
```

Then configure Claude Code to launch `python mcp_server/server.py` with `PROJECT_ROOT` pointing at the repo root. The server reads `backend/.env` for Supabase credentials and exposes 19 dev-automation tools (database queries, test runs, project introspection, migrations, agent fix/review) over stdio. See [CLAUDE.md](CLAUDE.md) for the full tool list.

## Environment Variables

### `frontend/.env`

```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
VITE_API_URL=http://localhost:8000
```

### `backend/.env`

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service role key>
ADMIN_SETUP_CODE=<one-time bootstrap code for the first super admin>
RESEND_API_KEY=<optional, for transactional email — Sprint 11>
FRONTEND_URL=http://localhost:5173
```

The backend uses the Supabase **service role key** for all reads and writes; the frontend never sees this key. See [CLAUDE.md](CLAUDE.md) for the two-client architecture and why row-level security is disabled on most tables.

## Testing

Tests are organized by sprint **and task** via pytest markers in [`backend/pytest.ini`](backend/pytest.ini). Each test file pins its sprint via `pytestmark = pytest.mark.sprintN`; per-method `@pytest.mark.sprintN_M` adds the task-level tag.

```powershell
cd backend
venv\Scripts\activate

# All tests
pytest tests/ -v --tb=short

# By sprint
pytest tests/ -v -m sprint1
pytest tests/ -v -m sprint2
pytest tests/ -v -m sprint3
pytest tests/ -v -m sprint4

# By task (fastest feedback during development)
pytest tests/ -v -m sprint4_2          # only the low-stock widget tests
pytest tests/ -v -m sprint4_6          # only the summary-report tests

# Single file or test
pytest tests/test_warranty.py -v
pytest tests/test_dashboard.py::TestSummaryReport -v

# Stop on first failure
pytest tests/ -v -x

# Watch Mode (auto-test on save, task-level)
.\mcp_server\agent\watch.ps1

# Pre-push review (full pytest + scans)
.\mcp_server\agent\review.ps1
```

Convenience scripts on Windows:

```powershell
.\run_tests.ps1                # all
.\run_tests.ps1 -Sprint 4      # sprint 4 only
```

### Test Coverage

Verified by `pytest tests/ -m sprintN --collect-only`. Full suite passes (169/169).

| Sprint | Tests | Status |
|--------|-------|--------|
| Sprint 1 | 12  | ✅ Passing |
| Sprint 2 | 30  | ✅ Passing |
| Sprint 3 | 88  | ✅ Passing |
| Sprint 4 | 41  | ✅ Passing |
| **Total** | **169** | **✅ all green** |

Test files (9): `test_auth.py`, `test_inventory.py`, `test_machine_lifecycle.py`, `test_warranty.py`, `test_reservations.py`, `test_issues.py`, `test_notifications.py`, `test_notification_bell.py`, `test_dashboard.py`.

## Sprint Roadmap

| Sprint | Focus | Status |
|--------|-------|--------|
| 0 | Project setup | ✅ Complete |
| 1 | Authentication & RBAC | ✅ Complete |
| 2 | Inventory & Batch Tracking | ✅ Complete |
| 3 | Machine Lifecycle & Warranty | ✅ Complete |
| 4 | Dashboard & Notifications | ✅ Complete |
| 5 | Leads & Customers | ⏳ Planned |
| 6 | Orders | ⏳ Planned |
| 7 | Commissions | ⏳ Planned |
| 8 | Tickets | ⏳ Planned |
| 9 | User Management & Settings | ⏳ Planned |
| 10 | Email & Polish | ⏳ Planned |
| 11 | Deployment | ⏳ Planned |

## Database

Supabase provides PostgreSQL plus authentication. The schema is created via the Supabase SQL Editor; canonical migration snippets live in the bug log and at the top of each router file.

15 tables in `public`: `profiles`, `invitations`, `admin_codes`, `admin_log`, `system_config`, `products`, `machines`, `consumable_stock`, `supplement_flavors`, `consumable_batches`, `machine_status_log`, `warranty`, `reservations`, `notifications`, `machine_issues`.

## API Documentation

Once the backend is running, interactive OpenAPI docs are available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Major endpoint groups (8 routers):

| Prefix | Purpose |
|--------|---------|
| `/api/auth/*` | Login, admin setup, invite rep, password change, admin codes/log |
| `/api/products`, `/api/machines`, `/api/consumable-*`, `/api/supplement-flavors` | Inventory CRUD |
| `/api/machines/{id}/status`, `/api/machines/status-summary`, `/api/machines/bulk-status` | Machine lifecycle |
| `/api/warranty/*` | Warranty CRUD, dashboard, expiring check, PDF certificates |
| `/api/reservations/*` | Reservation request / approve / deny / cancel / expire + analytics |
| `/api/issues/*` | Machine issue reporting, status, resolution |
| `/api/notifications/*` | List, unread-count, mark read, broadcast, clear-read |
| `/api/dashboard/summary`, `/api/dashboard/report`, `/api/activity` | Sprint 4 dashboard payloads |

## Key Architecture Decisions

- **`handle_new_user` Supabase trigger disabled** — profile creation happens in Python after `supabase.auth.admin.create_user()` returns (sprint-1 Bug 1.6).
- **Two Supabase clients** — `supabase` (user-context) and `supabase_admin` (service-role); never share one between user and admin operations (sprint-1 Bug 1.8).
- **Row-Level Security disabled** on most tables — backend uses `service_role` and enforces access in code (sprint-1 Bug 1.7).
- **Never use `.single()`** — always `.execute()` and check `result.data` (sprint-1 Bug 1.5).
- **Admin creates rep accounts with auto-generated passwords** — Supabase free-tier email is unreliable (sprint-1 Bug 1.9).
- **`consumable_stock.quantity` is a derived aggregate** (`SUM(consumable_batches.quantity)`), never edited directly (sprint-2 Bug 2.5).
- **Batch-level manufacturing traceability** — every consumable batch carries manufacture/expiry/shipment dates for health & safety compliance.
- **Friendly identifiers everywhere** — routes accept UUID, SKU, serial, or name; resolution in `find_by_identifier` (sprint-2 Bugs 2.1–2.3).
- **Static FastAPI routes before dynamic** — both within and across routers (sprint-2 Bug 2.8, sprint-3 Bug 3.9).
- **Full CRUD per resource** — no Create+Read with deferred Update/Delete (sprint-2 Bugs 2.6, 2.7).
- **Task-level test markers** — each Sprint 3/4 task has its own `sprintN_M` marker for granular execution (Watch Mode uses these).
- **Custom MCP server for development automation** — direct Supabase queries, pytest, project introspection, and Fix/Review modes inside Claude Code.
- **File watcher agent for auto-testing on save** — task-level resolution via `FILE_TO_MARKER` keeps feedback tight.

## Documentation

- [CLAUDE.md](CLAUDE.md) — codebase conventions, domain rules, current sprint state, MCP / agent reference
- [docs/bug-log/](docs/bug-log/) — every notable bug with symptom, root cause, fix, and prevention; indexed by sprint
- [docs/bug-log/README.md](docs/bug-log/README.md) — common patterns checklist; consult before debugging unfamiliar errors

## Author

**Henry (Huy) Bui** — Operations Analyst, Core Pacific Inc.

Full-stack development project combining ERP operations, manufacturing traceability, and sales management.

## License

Proprietary — Core Pacific Inc. All rights reserved.
