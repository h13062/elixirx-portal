# ElixirX Sales Portal — Bug Log System

## Purpose

This directory tracks every bug encountered during development of the ElixirX Sales Portal — what the symptom was, the root cause, and exactly how it was fixed. The goal is to avoid re-debugging the same class of problem twice.

**Before spending time debugging an unfamiliar error, check this log first.** A similar bug may have already been solved.

---

## Organization

One markdown file per sprint:

| File | Sprint |
|------|--------|
| [sprint-0.md](sprint-0.md) | Sprint 0 — Project setup, environment, tooling |
| [sprint-1.md](sprint-1.md) | Sprint 1 — Auth, database schema, backend foundation |
| [sprint-2.md](sprint-2.md) | Sprint 2 — Inventory module (products, machines, consumable stock, supplement flavors, batch tracking) |
| [sprint-3.md](sprint-3.md) | Sprint 3 — Machine lifecycle, warranty, reservations, issues, notifications, frontend auth refresh |

Add a new file (`sprint-N.md`) when a new sprint begins. Copy [TEMPLATE.md](TEMPLATE.md) as the starting point.

---

## Bug Entry Format

Each entry follows this structure:

```
## Bug N.X — [Short descriptive title]
- Date, Task, Severity, Symptom, Root Cause, Fix, Prevention, Files changed, Related bugs
```

See [TEMPLATE.md](TEMPLATE.md) for the full template.

**Severity levels:**
- **Blocker** — Cannot proceed with the sprint until resolved
- **Major** — Significant feature broken, workaround is painful
- **Minor** — Feature partially broken, easy workaround exists
- **Cosmetic** — UI/formatting issue, no functional impact

---

## Common Patterns

These recurring error types have known fixes. Check here before digging deeper.

### "Could not find the table 'public.X'"
The Python code references a table that does not exist in Supabase yet.
- **Fix:** Open the Supabase SQL Editor and run `CREATE TABLE` for the missing table.
- **Prevention:** Always create the DB schema before writing the Python that uses it.
- **See:** Bug 1.2, Bug 1.3

---

### `.single()` errors — "Cannot coerce the result to a single JSON object" (PGRST116)
Supabase's `.single()` throws if the query returns zero rows or more than one row.
- **Fix:** Replace every `.single()` call with `.execute()`, then check `result.data` length manually.
- **Prevention:** Never use `.single()`. Always use `.execute()` and guard with `if not result.data`.
- **See:** Bug 1.5

---

### Enum value errors — "unsafe use of new enum value"
PostgreSQL requires that an `ALTER TYPE ... ADD VALUE` statement is fully committed before any DDL that references the new value runs in the same transaction.
- **Fix:** Run the `ALTER TYPE` in a separate query, commit it, then run the `CREATE TABLE`.
- **Prevention:** Always add enum values as a standalone SQL statement before using them.
- **See:** Bug 1.1

---

### "Missing column" — column referenced in code doesn't exist
Code (or a Supabase trigger) references a column that was never added to the table.
- **Fix:** `ALTER TABLE table_name ADD COLUMN column_name TYPE;`
- **Prevention:** Keep schema migrations in a `/backend/migrations/` SQL file so the schema is always in sync with code.
- **See:** Bug 1.4

---

### RLS policy violations — 403 from Supabase on backend calls
Row Level Security policies that check `auth.uid()` always fail when called from the backend using the `service_role` key, because `auth.uid()` is `null` in that context.
- **Fix:** For backend-only tables (invitations, admin_log, etc.), disable RLS. The backend's `service_role` key bypasses RLS anyway — the policy is redundant and harmful.
- **Prevention:** Only enable RLS on tables that are accessed directly from the frontend/client with a user JWT.
- **See:** Bug 1.7

---

### Auth client contamination — "User not allowed" 403 on admin calls
When the same Supabase client instance is used for both user-authenticated requests and `supabase.auth.admin.*` calls, the internal auth state gets contaminated. The client ends up making admin calls with a user JWT instead of the service role key.
- **Fix:** Create a dedicated `supabase_admin` client (initialized with only the service role key) that is never used for user-facing calls.
- **Prevention:** Always maintain two separate clients: one for user context, one for admin operations.
- **See:** Bug 1.8

---

### Supabase trigger failures — "Database error creating new user"
A `BEFORE INSERT` or `AFTER INSERT` trigger on `auth.users` fails silently or with a generic error, blocking user creation.
- **Fix:** Disable the trigger. Handle the side effect (e.g., profile creation) in application code immediately after the auth call succeeds.
- **Prevention:** Avoid relying on Supabase database triggers for critical flows. Keep logic in Python where errors are visible and debuggable.
- **See:** Bug 1.6

---

### VS Code PATH issues — command not found after installing a tool
VS Code caches the PATH from the environment at the time it was opened. Tools installed after VS Code was opened are not on the PATH inside VS Code's terminal.
- **Fix:** Close and reopen VS Code after installing Node.js, Python, or any other CLI tool.
- **Prevention:** Install all required tools before opening VS Code for the session.
- **See:** Bug 0.2

---

### UUID vs friendly identifier — `invalid input syntax for type uuid`
Routes that filter `.eq("id", incoming_value)` against a UUID column reject any non-UUID value (SKUs, serial numbers, names) at the Postgres layer, even when those forms are the natural way an operator references the entity.
- **Fix:** Implement a `find_by_identifier(identifier)` method on the repository that tries UUID → SKU/serial → name (case-insensitive). Route handlers always go through this helper and use the resolved UUID downstream.
- **Prevention:** Treat raw UUIDs as internal-only. Any path/query/body identifier exposed at the API boundary must accept the human-friendly form. Code review red flag: `.eq("id", <route param>)` against a UUID column.
- **See:** Bug 2.1, Bug 2.2, Bug 2.3

---

### Simple stock vs lot-tracked stock — model regulated/perishable products with batches from day one
Treating a consumable as a single `quantity` integer per product makes flavor variants, manufacture/expiry dates, and shipment-to-batch traceability impossible to add later without a model rewrite.
- **Fix:** Three-table shape — `products` (catalog) → `consumable_stock` (derived aggregate: `quantity = SUM(batches.quantity)`) → `consumable_batches` (source of truth with manufacture_date, expiry_date, batch_number, shipped_date). Recalculate the aggregate after every batch mutation.
- **Prevention:** During design, walk the entity through its full physical lifecycle (manufactured → packaged → shipped → returned → recalled → expired). Any state without a data home means the model is incomplete.
- **See:** Bug 2.5

---

### Always ship full CRUD — half-CRUD becomes a permanent ops tax
Shipping `Create + Read` and deferring `Update + Delete` pushes admins into the database to do basic edits (rename, fix typo, remove duplicate). The "later" rarely happens until the operational pain is high.
- **Fix:** For every new resource, build all four verbs in the same PR. Decide soft-delete (entity has historical references) vs hard-delete (pure mistake-removal) up front and document it on the endpoint.
- **Prevention:** PR review checklist item — "Does this resource have all four CRUD operations? If not, where is the ticket?" Treat partial CRUD as a known cost, not a milestone.
- **See:** Bug 2.6, Bug 2.7

---

### FastAPI route ordering — static paths before path parameters
Within a router, FastAPI matches routes in registration order. A static segment like `/foo/report` declared *after* `/foo/{id}` will be captured as `id="report"` and never reach its handler.
- **Fix:** Declare every static path before any `{param}` path that shares the same prefix. Group statics at the top of the file with a comment marking the boundary.
- **Prevention:** When mixing static and parameterized routes, prefer a more specific sub-prefix for the static endpoints (e.g., `/foo-reports/summary`) so collisions are impossible by construction.
- **See:** Bug 2.8

---

### Buried inline edit affordances — promote to clickable card + modal
Tiny pencil/icon buttons inside a card or row become invisible to users and don't scale when more actions need to be added. Operators bypass the UI entirely and edit data in the database.
- **Fix:** Make the card itself clickable (with a visible hover state) and open a dedicated modal that hosts the full management surface — header, summary stats, related entity tabs, action table, settings.
- **Prevention:** If the third action you want to add to a card doesn't fit comfortably in the existing layout, move all actions to a modal. Don't keep stacking icon buttons.
- **See:** Bug 2.4

---

### PostgREST embed syntax — column-named alias vs FK relation
Embedding a related table over a foreign key uses `<table>(...)` (PostgREST resolves the FK automatically), not `<table>:<column>(...)`. The colon form is only needed when the same target table is referenced by **two or more** FKs on the source row, in which case use `relation!fk_column(...)` to disambiguate.
- **Symptom:** "Could not find a relationship between 'X' and 'Y' in the schema cache."
- **Fix:** Use `profiles(full_name)` for a single FK; `reserved_by_profile:profiles!reserved_by(full_name)` and `approved_by_profile:profiles!approved_by(full_name)` for two FKs to the same table.
- **Prevention:** Grep the destination table's actual column names before writing the select string — `name` vs `full_name` is a one-character bug that compiles and only fails at request time.
- **See:** Bug 3.2

---

### Silent Postgrest exceptions — never wrap mutations in `try/except: pass`
A bare `try/except: pass` around a database insert masks both schema mismatches and real outages. The action looks like it succeeded; nothing actually wrote.
- **Symptom:** Tests pass, manual flows look fine, but downstream consumers (admins, dashboards) see nothing.
- **Fix:** Always log the exception, even when the action is best-effort. Route writes that come from many call sites through a single helper so the logging happens in one place.
- **Prevention:** Code review red flag: any `except Exception: pass` next to a `.insert()` or `.update()`. Promote it to `except Exception as e: logger.exception(...)`.
- **See:** Bug 3.5

---

### 404 = "no record yet," not "error"
Endpoints that lookup-by-key for an entity that may not exist yet (warranty for a machine, reservation for a machine, profile by email) return 404 by HTTP convention. The frontend must distinguish that 404 from a 500 / network failure.
- **Symptom:** A red error banner appears on a page that's actually working — the user just hasn't created the related record yet.
- **Fix:** Use `apiGetOptional<T>()` from `frontend/src/lib/api.ts` — returns `null` on 404, throws on every other non-OK status.
- **Prevention:** On every `GET /resource/lookup-key/{key}` route, decide whether 404 is a normal state. If yes, document it and verify the frontend uses `apiGetOptional` rather than `apiGet`.
- **See:** Bug 3.6

---

### Auth wrapper coverage — migrate every call site in the same PR
When introducing a wrapper meant to be the canonical entry point for a class of calls (auth, caching, telemetry), the success criterion is **zero direct calls to the underlying primitive outside the wrapper file**.
- **Symptom:** A bug that's "fixed" still reproduces on certain pages — because those pages still call the underlying primitive directly.
- **Fix:** Project-wide `grep -rn 'await fetch' frontend/src` after introducing the wrapper. Convert every match outside `lib/api.ts`. Don't leave "I'll migrate the rest later" comments.
- **Prevention:** Bake the grep into the PR description as a verification step. Code review red flag: any direct `fetch()` call in a page or component that includes an `Authorization` header.
- **See:** Bug 3.7, Bug 3.8

---

### Cross-router static priority — `include_router` order matters when prefixes overlap
Sprint 2 Bug 2.8 was about static-before-dynamic **within** a router. Sprint 3 Bug 3.9 extends the same rule to **across** routers: when two routers share a path prefix and one owns a `{param}` route at that prefix, the static-route router must be `app.include_router()`'d first.
- **Symptom:** A literal path returns the same UUID-parse error you'd get from passing a non-UUID to a dynamic route — but the route is in a different router.
- **Fix:** Reorder the `include_router` calls so static-route routers come first. Or give static endpoints a more specific sub-prefix that can't collide.
- **Prevention:** When adding a new router, list every prefix it overlaps with and verify the `include_router` order. Better: design URL prefixes to be non-overlapping by construction.
- **See:** Bug 3.9, Bug 2.8

---

## How to Maintain This Log

1. **Log every bug that takes more than 5 minutes to resolve.** If it stumped you, it will stump someone (or future you) again.

2. **Write for 6-months-later you.** Include the exact error message, what you tried that did not work, and what finally fixed it. Don't assume context.

3. **Cross-reference related bugs.** Use the "Related bugs" field to link entries with similar root causes. This reveals patterns over time.

4. **Update the Common Patterns section** when a new recurring error type is confirmed across two or more sprints.

5. **One file per sprint.** Start a new `sprint-N.md` at the beginning of each sprint, even if it stays empty — it marks the boundary clearly.

6. **Commit the log alongside the code fix.** The git history then ties the bug entry to the diff that resolved it.
