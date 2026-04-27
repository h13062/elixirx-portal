# ElixirX Sales Portal — Codebase Notes

Project context for AI assistants. The README is for human onboarding; this file
captures architectural conventions and domain rules that aren't obvious from
reading the code.

## Architecture

- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4. Pages in `frontend/src/pages/`, feature components in `frontend/src/components/<feature>/`.
- **Backend:** FastAPI + Supabase Python client, organized as **thin router → service → repository → Supabase**. All business logic lives in services; routers are HTTP-only adapters; repositories own table access.
  - `backend/app/routers/` — FastAPI route handlers
  - `backend/app/services/` — business logic
  - `backend/app/repositories/` — Supabase table access (one class per table)
  - `backend/app/models/` — Pydantic request/response models
  - `backend/app/core/` — auth, Supabase clients, config
- **Two Supabase clients:** `supabase` (user-context) and `supabase_admin` (service-role). All backend reads/writes use `supabase_admin`. See [docs/bug-log/sprint-1.md](docs/bug-log/sprint-1.md) Bug 1.8 — sharing a single client between user and admin operations causes auth contamination.

## Core Conventions

- **Never use `.single()`.** Always `.execute()` and check `result.data[0]`. See sprint-1 Bug 1.5.
- **Friendly identifiers everywhere.** Routes that take an entity reference (product, machine, flavor) accept UUID **or** SKU/serial/name. Resolution lives in the repository (`find_by_identifier`). See sprint-2 Bugs 2.1–2.3.
- **Static FastAPI routes before dynamic ones.** A static segment like `/foo/report` declared after `/foo/{id}` will be captured as `id="report"`. See sprint-2 Bug 2.8.
- **Cross-router static priority:** when a static path in one router (e.g. `/machines/status-summary`) shares a prefix with a dynamic path in another router (`/machines/{machine_id}`), the static-route router must be registered **first** in `main.py`.
- **Full CRUD per resource.** Don't ship Create+Read and defer Update/Delete — admins end up editing Postgres by hand. See sprint-2 Bug 2.6, 2.7.
- **Bug log:** every non-trivial bug goes in [docs/bug-log/](docs/bug-log/). Check there before debugging unfamiliar errors.

## Sprint Order (Updated)

| Sprint | Focus | Status |
|--------|-------|--------|
| 0 | Project Setup | ✅ Complete |
| 1 | Authentication | ✅ Complete |
| 2 | Inventory (machines, consumables, batch tracking, flavors) | ✅ Complete |
| 3 | Machine Lifecycle & Warranty | 🔄 In Progress (3.1 built) |
| 4 | Dashboard & Notifications | Pending |
| 5 | Leads & Customers | Pending |
| 6 | Orders | Pending |
| 7 | Commissions | Pending |
| 8 | Tickets | Pending |
| 9 | User Management & Settings | Pending |
| 10 | Email & Polish | Pending |
| 11 | Deployment | Pending |

## Sprint 3 Tasks

| Task | What | Status |
|------|------|--------|
| 3.0 | Database migration (machine_status_log, warranty, reservations, notifications, machine_issues) | ✅ Done |
| 3.1 | Backend: machine status transitions with logging | ✅ Built, tests enabled |
| 3.2 | Backend: warranty endpoints (set, extend, check expiring, PDF) | Pending |
| 3.3 | Backend: reservation endpoints (request, approve, deny, expire) | Pending |
| 3.4 | Backend: machine issues endpoints (report, track, resolve) | Pending |
| 3.5 | Backend: notification endpoints (create, list, mark read) | Pending |
| 3.6 | Machine detail page UI | Pending |
| 3.7 | Admin machine actions UI | Pending |
| 3.8 | Warranty page UI | Pending |
| 3.9 | Reservation UI | Pending |

## Sprint 4 Preview (Dashboard & Notifications)

Dashboard will include:
- Warranty expiration alerts (30 days before)
- Low stock alerts (consumables below `min_threshold`)
- Machine status change log (who, what, when)
- Issues tracker
- Daily/weekly summary report

## Key Decisions

- **[DECISION]** `handle_new_user` trigger is DISABLED — profile creation handled in Python (sprint-1 Bug 1.6).
- **[DECISION]** RLS disabled on most tables — backend uses `service_role` key and handles access control (sprint-1 Bug 1.7).
- **[DECISION]** Two Supabase clients: `supabase` (regular) and `supabase_admin` (for `auth.admin.*` calls and all backend writes) (sprint-1 Bug 1.8).
- **[DECISION]** Never use `.single()` — always `.execute()` + check `result.data` (sprint-1 Bug 1.5).
- **[DECISION]** Admin creates rep accounts directly with auto-generated passwords (sprint-1 Bug 1.9 — Supabase free-tier email is unreliable).
- **[DECISION]** Each supplement flavor has its own SKU (`SUPP-FA` through `SUPP-FE`).
- **[DECISION]** Consumable batches tracked with manufacturing traceability (`manufacture_date`, `shipped_date`, `shipped_to`); `consumable_stock.quantity` is a derived `SUM(batches.quantity)` aggregate, not a source of truth.
- **[DECISION]** Sprint order changed: Machine Lifecycle (Sprint 3) and Dashboard (Sprint 4) prioritized before Leads/Customers/Orders.

## Inventory Domain

### Stock model — derived aggregate

`consumable_stock.quantity` is **not** a source of truth. It is recalculated as `SUM(consumable_batches.quantity)` after every batch insert/update/delete/ship via `InventoryService._recalculate_stock(product_id)`. Editing it directly bypasses the invariant.

### Supplement Pack — flavored consumable

The supplement product has variants tracked in `supplement_flavors`. Batches for the supplement pack **must** carry a `flavor_id`; batches for any other consumable **must not**. See `InventoryService.create_batch` validation.

## Machine Lifecycle (Sprint 3+)

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

### Lifecycle endpoints

All under `/api`, registered in `main.py` **before** `inventory_router` so static routes win:

- `GET /api/machines/status-summary` — counts grouped by status (no auth gate beyond logged-in)
- `POST /api/machines/bulk-status` (admin) — apply same status to multiple machines, errors collected per-id
- `PUT /api/machines/{identifier}/status` (admin) — single transition; response shape `{ machine: MachineResponse, warranty_setup_required: bool }`. Returns `warranty_setup_required: true` when transitioning to `delivered` so the frontend can prompt warranty setup
- `GET /api/machines/{identifier}/status-history` — full log for one machine, joined to `profiles` for `changed_by_name`
- `GET /api/machines/{identifier}/full-detail` — machine + product + last 10 status entries + warranty + active reservation + open issues. The warranty/reservation/issue lookups are best-effort: if the table doesn't exist yet (future sprint), the field is returned as `null`/`[]` instead of erroring.

## Database Tables

- **Sprint 0–1:** `profiles`, `invitations`, `admin_codes`, `admin_log`, `system_config`
- **Sprint 2:** `products`, `machines`, `consumable_stock`, `supplement_flavors`, `consumable_batches`
- **Sprint 3:** `machine_status_log`, `warranty`, `reservations`, `notifications`, `machine_issues`

## Test Accounts

- Super Admin: `bgh.huybui@gmail.com` / `Huy13062` (role: super_admin)
- Admin: `bgh1506@gmail.com` / `Huy13062` (role: admin)
- Rep: `minh.tran@example.com` / `Minh2026!` (role: rep, tier: agent)

## Testing

- Run all tests: `cd backend && venv\Scripts\activate && pytest tests/ -v --tb=short`
- Run one file: `pytest tests/test_machine_lifecycle.py -v`
- Run one test: `pytest tests/test_auth.py::TestLogin::test_login_super_admin -v`
- Stop on first failure: `pytest tests/ -v -x`
- Convenience scripts: `backend/run_tests.bat` (CMD) or `backend/run_tests.ps1` (PowerShell)
- Test credentials live in [backend/tests/conftest.py](backend/tests/conftest.py) — three sessions: super_admin, admin, rep
- Test data uses a `TEST-` / `RX-` / `LOT-` / `SKU-` prefix (with random suffix via `unique_id()`) for easy identification and cleanup
- pytest config at [backend/pytest.ini](backend/pytest.ini) sets `pythonpath = . tests` so `from conftest import unique_id` resolves
- 65 tests collected; Sprint 3 lifecycle tests are now active (no skips)
- ALWAYS run tests before `git push`

## Documentation

- [docs/bug-log/](docs/bug-log/) — every notable bug with symptom, root cause, fix, prevention. Indexed by sprint.
- [docs/bug-log/README.md](docs/bug-log/README.md) — common patterns checklist; consult before debugging.
