# ElixirX Sales Portal

A full-stack sales operations platform for Core Pacific Inc.'s ElixirX hydrogen water product line. Built with React, FastAPI, and Supabase.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | Python + FastAPI |
| Database | Supabase (PostgreSQL + Auth) |
| Testing | pytest with sprint-based markers |
| Version Control | Git + GitHub |

## Features

### Sprint 1 — Authentication
- Role-based access control (Super Admin, Admin, Sales Rep)
- Three rep tiers: Distributor (10%), Agent (10-20%), Master Agent (25%)
- Admin creates rep accounts with auto-generated temporary passwords
- Password change functionality
- Session management with JWT tokens
- Protected routes with role-based sidebar navigation

### Sprint 2 — Inventory Management
- Machine registration with serial number tracking (RX Machine $5,995 / RO Machine $3,995)
- Consumable stock with batch-level traceability
- Manufacturing date and shipment tracking for health & safety compliance
- Supplement flavor management with individual SKUs (SUPP-FA through SUPP-FE)
- Full CRUD for products, flavors, and batches
- Friendly identifier lookup (UUID, SKU, or name accepted on all endpoints)
- Low stock alerts with configurable thresholds

### Sprint 3 — Machine Lifecycle & Warranty (In Progress)
- Machine status transitions: Available → Reserved → Ordered → Sold → Delivered → Returned
- Every status change logged with who/when/why
- Force override for admin with audit trail
- Warranty tracking with creation, extension, and PDF certificate generation
- Warranty dashboard: active, expiring soon (30 days), expired counts
- Reservation workflow: rep requests → admin approves/denies → 7-day countdown → auto-expiry
- Machine issue tracking with priority levels (Low/Medium/High/Urgent)
- Issue resolution workflow with admin notes

## Project Structure

```
elixirx-portal/
├── frontend/                       # React + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── pages/                  # Route-level views (Login, Dashboard, Inventory, ...)
│   │   ├── components/             # Feature components (inventory/, layout, etc.)
│   │   ├── context/                # ThemeContext, auth context
│   │   ├── lib/                    # API client, Supabase client
│   │   └── main.tsx
│   ├── index.html
│   └── package.json
├── backend/                        # FastAPI application
│   ├── app/
│   │   ├── routers/                # HTTP-only adapters (auth, inventory,
│   │   │                           #   machine_lifecycle, warranty,
│   │   │                           #   reservations, issues)
│   │   ├── services/               # Business logic
│   │   ├── repositories/           # One class per Supabase table
│   │   ├── models/                 # Pydantic request/response models
│   │   ├── core/                   # Auth, Supabase clients, helpers, config
│   │   └── main.py                 # App entrypoint + router registration
│   ├── tests/                      # pytest suite (markers: sprint1/2/3)
│   ├── pytest.ini
│   ├── run_tests.ps1               # PowerShell runner: .\run_tests.ps1 -Sprint 3
│   ├── run_tests.bat               # CMD runner: run_tests.bat 3
│   └── requirements.txt
├── docs/
│   └── bug-log/                    # Per-sprint bug log
├── CLAUDE.md                       # Architectural conventions and domain rules
└── README.md                       # This file
```

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- A Supabase project (free tier works for development)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at http://localhost:5173.

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Runs at http://localhost:8000. Interactive API docs at http://localhost:8000/docs. Health check at http://localhost:8000/api/health.

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

Tests are organized by sprint via pytest markers in [backend/pytest.ini](backend/pytest.ini). Each test file pins its sprint via `pytestmark = pytest.mark.sprintN`.

```bash
cd backend
venv\Scripts\activate

# All tests
pytest tests/ -v --tb=short

# Run by sprint
pytest tests/ -v -m sprint1
pytest tests/ -v -m sprint2
pytest tests/ -v -m sprint3

# Single file or test
pytest tests/test_warranty.py -v
pytest tests/test_warranty.py::TestWarranty::test_create_warranty -v

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

Supabase provides PostgreSQL plus authentication. The schema is created via the Supabase SQL Editor; canonical migration snippets live in the bug log and at the top of each router file (e.g. [backend/app/routers/auth_router.py](backend/app/routers/auth_router.py)).

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

Major endpoint groups:

| Prefix | Purpose |
|--------|---------|
| `/api/auth/*` | Login, admin setup, invite rep, password change |
| `/api/products`, `/api/machines`, `/api/consumable-*`, `/api/supplement-flavors` | Inventory |
| `/api/machines/{id}/status`, `/api/machines/status-summary`, `/api/machines/bulk-status` | Machine lifecycle |
| `/api/warranty/*` | Warranty CRUD, dashboard, PDF certificates |
| `/api/reservations/*` | Reservation request / approve / deny / cancel |
| `/api/issues/*` | Machine issue reporting and resolution |

## Documentation

- [CLAUDE.md](CLAUDE.md) — codebase conventions, domain rules, and architectural decisions for AI assistants and human contributors
- [docs/bug-log/](docs/bug-log/) — every notable bug with symptom, root cause, fix, and prevention; indexed by sprint
- [docs/bug-log/README.md](docs/bug-log/README.md) — common patterns checklist; consult before debugging unfamiliar errors

## License

Proprietary — Core Pacific Inc. All rights reserved.
