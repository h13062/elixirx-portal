# ElixirX Sales Portal

A full-stack sales operations platform for Core Pacific Inc.'s ElixirX hydrogen water product line. Built with React, FastAPI, and Supabase.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | Python + FastAPI |
| Database | Supabase (PostgreSQL + Auth) |
| Testing | pytest with sprint-based markers |
| Dev tools | `elixirx-dev` MCP server + Development Agent (watch/review/fix) |
| Version Control | Git + GitHub |

## Features

### Sprint 1 — Authentication ✅
- Role-based access control (Super Admin, Admin, Sales Rep)
- Three rep tiers: Distributor (10%), Agent (10–20%), Master Agent (25%)
- Admin creates rep accounts with auto-generated temporary passwords
- Password change functionality
- Session management with JWT tokens, frontend auto-refresh on 401
- Protected routes with role-based sidebar navigation

### Sprint 2 — Inventory Management ✅
- Machine registration with serial number tracking (RX Machine $5,995 / RO Machine $3,995)
- Consumable stock with batch-level traceability (manufacture date, expiry, shipment-to)
- Supplement flavor management with individual SKUs (`SUPP-FA` … `SUPP-FE`)
- Full CRUD for products, flavors, machines, and batches (soft delete + hard delete decided per resource)
- Friendly identifier lookup — UUID, SKU, or name accepted on every endpoint
- Low-stock detection with configurable per-product thresholds

### Sprint 3 — Machine Lifecycle, Warranty & Notifications ✅
- Machine status transitions: `available → reserved → ordered → sold → delivered → returned`, every change logged with who/when/why
- Admin force override (skips state-machine check, prefixes reason with `FORCED:`)
- Warranty tracking: create, extend, PDF certificate generation (fpdf2), expiring/expired dashboard
- Reservation workflow: rep requests → admin approves/denies → 7-day countdown → auto-expiry, plus by-account analytics with sortable rep filter
- Issue tracking with priority levels (Low/Medium/High/Urgent) and resolution notes
- In-app notifications with `notify_admins` / `notify_user` helpers wired into reservation, warranty, and issue events
- **Frontend:** three-tab Inventory, Machine Detail page with full lifecycle UI, Warranty page with dashboard tab, Issues page

### Sprint 4 — Dashboard & Notifications 🔄 (in progress)
- ✅ 4.0 Single-endpoint dashboard summary (`GET /api/dashboard/summary`) aggregates 9 sections in one round trip
- ✅ 4.1 Warranty expiration alerts widget — extend / download certificate inline
- ✅ 4.2 Low stock alerts widget — mini cards with progress bars, OUT OF STOCK badge, pulsing critical indicator
- ⏳ 4.3 Activity feed (data already in summary; UI pending)
- ⏳ 4.4 Issue tracker widget (data already in summary; UI pending)
- ⏳ 4.5 Notification bell
- ⏳ 4.6 Summary reports
- ⏳ 4.7 Role-based views
- ⏳ 4.8 Sprint-4 full test pass

## Sprint Roadmap

| Sprint | Focus | Status |
|--------|-------|--------|
| 0  | Project setup | ✅ Complete |
| 1  | Authentication | ✅ Complete |
| 2  | Inventory & Batch Tracking | ✅ Complete |
| 3  | Machine Lifecycle & Warranty | ✅ Complete |
| 4  | Dashboard & Notifications | 🔄 In progress (4.0–4.2 done) |
| 5  | Leads & Customers | ⏳ Pending |
| 6  | Orders | ⏳ Pending |
| 7  | Commissions | ⏳ Pending |
| 8  | Tickets | ⏳ Pending |
| 9  | User Management & Settings | ⏳ Pending |
| 10 | Email & Polish | ⏳ Pending |
| 11 | Deployment | ⏳ Pending |

## Test Coverage

138 tests in 8 files. Verified by `pytest tests/ --collect-only -q -m sprintN`.

| Sprint | Tests | Status |
|--------|-------|--------|
| Sprint 1 | 12  | ✅ Passing |
| Sprint 2 | 30  | ✅ Passing |
| Sprint 3 | 88  | ✅ Passing |
| Sprint 4 | 10  | ✅ Passing (tasks 4.0–4.2) |
| **Total** | **138** | |

Test files: `test_auth.py`, `test_inventory.py`, `test_machine_lifecycle.py`, `test_warranty.py`, `test_reservations.py`, `test_issues.py`, `test_notifications.py`, `test_dashboard.py`.

## Project Structure

```
elixirx-portal/
├── frontend/                       # React + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── pages/                  # 14 route-level views (Dashboard, Inventory,
│   │   │                           #   MachineDetail, Warranty, Issues, ...)
│   │   ├── components/             # Feature components (inventory/, layout/, ...)
│   │   ├── context/                # Theme + auth context
│   │   ├── lib/                    # api client (with auth refresh), download helpers
│   │   └── main.tsx
│   ├── index.html
│   └── package.json
├── backend/                        # FastAPI application
│   ├── app/
│   │   ├── routers/                # 8 routers — auth, inventory, machine_lifecycle,
│   │   │                           #   warranty, reservations, issues, notifications,
│   │   │                           #   dashboard
│   │   ├── services/               # Business logic
│   │   ├── repositories/           # One class per Supabase table
│   │   ├── models/                 # Pydantic request/response models
│   │   ├── core/                   # Auth, Supabase clients, helpers,
│   │   │                           #   notification_helper, config
│   │   └── main.py                 # App entrypoint + router registration
│   ├── tests/                      # 8 test files, 138 tests, sprint markers
│   ├── pytest.ini
│   ├── run_tests.ps1               # PowerShell runner: .\run_tests.ps1 -Sprint 3
│   ├── run_tests.bat               # CMD runner: run_tests.bat 3
│   └── requirements.txt
├── mcp_server/                     # elixirx-dev MCP server (dev automation)
│   ├── server.py                   # Stdio entrypoint
│   ├── tools/                      # database, testing, project, migration
│   └── requirements.txt
├── docs/
│   └── bug-log/                    # Per-sprint bug log (sprints 0–4)
├── CLAUDE.md                       # Architectural conventions + current state
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

### MCP Server (optional, for Claude Code automation)

```powershell
cd mcp_server
pip install -r requirements.txt
# Then configure Claude Code to launch python mcp_server/server.py
# with PROJECT_ROOT set to the repo root.
```

The server reads `backend/.env` for Supabase credentials and exposes 19 dev-automation tools (database queries, test runs, project introspection, migrations, agent fix/review) over stdio. See [CLAUDE.md](CLAUDE.md) for the full tool list.

### Development Agent (optional, terminal-based)

The agent at [`mcp_server/agent/`](mcp_server/agent/) gives you two terminal modes and two Claude-Code MCP tools that share the same failure state.

```powershell
# Watch Mode — auto-runs sprint tests on file save (also `npx tsc --noEmit` for .ts/.tsx).
.\mcp_server\agent\watch.ps1

# Review Mode — pre-push checks: full pytest, debug artifacts, secrets, .env exposure, coverage gaps.
.\mcp_server\agent\review.ps1
```

From inside Claude Code:

- *"Use elixirx-dev to diagnose the last test failure"* — pattern-matches the most recent watcher failure (missing table, `.single()`, 401/403/404, UUID friendly-id, …)
- *"Use elixirx-dev to auto-fix the failing tests"* — turns the diagnosis into a step list with files to read
- *"Use elixirx-dev to run pre-push review"* — same six checks as `review.ps1`

The watcher writes failures to `mcp_server/agent/last_failure.json`; the review writes its JSON report to `last_review.json` alongside it.

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

The backend uses the Supabase service role key for all reads and writes; the frontend never sees this key. See [CLAUDE.md](CLAUDE.md) for the two-client architecture and why row-level security is disabled on most tables.

## Running Tests

Tests are organized by sprint and task via pytest markers in [`backend/pytest.ini`](backend/pytest.ini). Each test file pins its sprint via `pytestmark = pytest.mark.sprintN`; per-method `@pytest.mark.sprintN_M` adds the task-level tag.

```powershell
cd backend
venv\Scripts\activate

# All tests
pytest tests/ -v --tb=short

# By sprint
pytest tests/ -v -m sprint1
pytest tests/ -v -m sprint3
pytest tests/ -v -m sprint4

# By task (during development)
pytest tests/ -v -m sprint4_2

# Single file or test
pytest tests/test_warranty.py -v
pytest tests/test_dashboard.py::TestLowStockAlerts -v

# Stop on first failure
pytest tests/ -v -x
```

Convenience scripts on Windows:

```powershell
.\run_tests.ps1                # all
.\run_tests.ps1 -Sprint 3      # sprint 3 only
```

```bat
run_tests.bat                  REM all
run_tests.bat 3                REM sprint 3 only
```

## Database

Supabase provides PostgreSQL plus authentication. The schema is created via the Supabase SQL Editor; canonical migration snippets live in the bug log and at the top of each router file.

15 tables in `public`: `profiles`, `invitations`, `admin_codes`, `admin_log`, `system_config`, `products`, `machines`, `consumable_stock`, `supplement_flavors`, `consumable_batches`, `machine_status_log`, `warranty`, `reservations`, `notifications`, `machine_issues`.

Notable architectural decisions (full list in [CLAUDE.md](CLAUDE.md)):

- The `handle_new_user` Supabase trigger is **disabled** — profile creation happens in Python after `supabase.auth.admin.create_user()` returns.
- Row-Level Security is **disabled** on most tables — the backend uses the `service_role` key and enforces access in code.
- `consumable_stock.quantity` is a **derived aggregate** (`SUM(consumable_batches.quantity)`); never edit it directly.
- Every machine status change writes a row to `machine_status_log` — no exceptions, including bulk and forced transitions.
- API routes accept either UUID **or** human-friendly identifiers (SKU, serial number, name). Resolution lives in repositories or the shared `app/core/helpers.py`.

## API Documentation

Once the backend is running, interactive OpenAPI docs are available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Major endpoint groups (8 routers):

| Prefix | Purpose |
|--------|---------|
| `/api/auth/*` | Login, admin setup, invite rep, password change, admin codes/log |
| `/api/products`, `/api/machines`, `/api/consumable-*`, `/api/supplement-flavors` | Inventory CRUD |
| `/api/machines/{id}/status`, `/api/machines/status-summary`, `/api/machines/bulk-status`, `/full-detail`, `/status-history` | Machine lifecycle |
| `/api/warranty/*` | Warranty CRUD, dashboard, expiring check, PDF certificates |
| `/api/reservations/*` | Reservation request / approve / deny / cancel / expire + analytics |
| `/api/issues/*` | Machine issue reporting, status, resolution |
| `/api/notifications/*` | List, unread-count, mark read, broadcast, clear-read |
| `/api/dashboard/summary` | Sprint 4 — full dashboard payload in one call |

## Documentation

- [CLAUDE.md](CLAUDE.md) — codebase conventions, domain rules, current sprint state, MCP server reference
- [docs/bug-log/](docs/bug-log/) — every notable bug with symptom, root cause, fix, and prevention; indexed by sprint
- [docs/bug-log/README.md](docs/bug-log/README.md) — common patterns checklist; consult before debugging unfamiliar errors

## License

Proprietary — Core Pacific Inc. All rights reserved.
