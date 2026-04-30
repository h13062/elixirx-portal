# Sprint 3 — Bug Log

Sprint 3 covers the machine lifecycle module: status transitions with audit logging, warranty (CRUD + PDF certificates), reservations (request → approve/deny → 7-day countdown → expire), machine issues, in-app notifications, and the UI for all of the above (Machine Detail page, Inventory tabs, Warranty page, Reservations tab + analytics).

Bugs in this sprint cluster around four themes: **schema drift** (tables/columns assumed but not created), **PostgREST embed syntax** (joining via FK columns vs relations), **frontend auth wrapper coverage** (the `fetchWithAuth` refresh mechanism shipped but several files still called raw `fetch()`), and **404 ergonomics** (endpoints that legitimately return 404 for "no record yet" being rendered as errors).

---

## Bug 3.1 — `machine_status_log` table missing (PGRST205)

- **Date:** 2026-04-22
- **Task:** 3.1 (machine status transitions)
- **Severity:** Blocker
- **Symptom:** Every status transition on a machine returned a 500 with the error `Failed to update machine status: {'code': 'PGRST205', 'message': "Could not find the table 'public.machine_status_log' in the schema cache"}`. Tests for Sprint 3.1 all failed with the same message.
- **Root Cause:** The Sprint 3.0 migration script (`docs/sprint-3-migration.sql`) was written but never executed against Supabase. The `machine_lifecycle_service` insert into `machine_status_log` was the first call to reference the table, so the missing-table error only surfaced when a status transition was attempted.
- **Fix:** Ran the Sprint 3.0 migration in the Supabase SQL Editor. Confirmed via `select * from machine_status_log limit 1` that the table existed with the expected columns (`machine_id`, `from_status`, `to_status`, `changed_by`, `reason`, `created_at`).
- **Prevention:** When a sprint introduces new tables, the migration must be applied **before** any code that depends on it is merged. CLAUDE.md now lists the Sprint 3 tables under "Database Tables" so the dependency is visible at the start of the sprint, not discovered at the first failing test.
- **Files changed:**
  - `docs/sprint-3-migration.sql` (executed against Supabase)
- **Related bugs:** [Bug 3.5 — `notifications.read` vs `is_read`](#bug-35--notifications-column-name-read-vs-is_read)

---

## Bug 3.2 — Wrong PostgREST embed syntax for `changed_by` profile join

- **Date:** 2026-04-22
- **Task:** 3.1 (status history endpoint)
- **Severity:** Major
- **Symptom:** `GET /api/machines/{identifier}/status-history` returned 400:

  ```
  {"message": "Could not find a relationship between 'machine_status_log' and 'changed_by' in the schema cache"}
  ```

  The intent was to embed the rep's display name alongside each log row, but PostgREST rejected the embed.

- **Root Cause:** Two issues stacked on the same select string. First, the original code wrote `profiles:changed_by(name)`. The colon-form `<alias>:<column>` is for selecting from a foreign-relationship by **column name** — but only when the column itself is the FK. PostgREST resolves the relationship from the `changed_by` FK on `machine_status_log` to `profiles.id`, so the simple form `profiles(...)` is what's needed. Second, the column on `profiles` is `full_name`, not `name` — so even after the syntax was fixed, the join would have returned a `null` for the field.
- **Fix:** Changed every `_LOG_SELECT` / `_RESERVATION_SELECT` / `_WARRANTY_SELECT` to use plain `profiles(full_name)`:

  ```python
  _LOG_SELECT = (
      "id, machine_id, from_status, to_status, changed_by, reason, "
      "created_at, profiles(full_name)"
  )
  ```

  For tables with **two** FKs to `profiles` (e.g. `reservations.reserved_by` and `reservations.approved_by`), used the explicit `relation!fk_column(...)` disambiguation:

  ```python
  _RESERVATION_SELECT = (
      "*, machines(serial_number, products(name)), "
      "reserved_by_profile:profiles!reserved_by(full_name), "
      "approved_by_profile:profiles!approved_by(full_name)"
  )
  ```

- **Prevention:** Whenever embedding a related table over a FK, prefer `<table>(...)` (PostgREST resolves the FK automatically). Use `relation!fk_column(...)` only when the same target table is referenced by more than one FK. Always grep the destination table's actual column names before writing the select string — `name` vs `full_name` is a one-character bug that compiles and only fails at request time.
- **Files changed:**
  - `backend/app/repositories/machine_status_log_repository.py`
  - `backend/app/services/machine_lifecycle_service.py`
  - `backend/app/routers/reservations.py`
  - `backend/app/routers/warranty.py`
- **Related bugs:** [Bug 3.5](#bug-35--notifications-column-name-read-vs-is_read) — same class of "code disagrees with actual column name."

---

## Bug 3.3 — `'ProductRepository' object has no attribute 'find_by_id'`

- **Date:** 2026-04-23
- **Task:** 3.1 (`GET /api/machines/{id}/full-detail`)
- **Severity:** Blocker
- **Symptom:** The full-detail endpoint returned 500 on every call:

  ```
  AttributeError: 'ProductRepository' object has no attribute 'find_by_id'
  ```

  This blocked the entire Machine Detail page, which depends on this single endpoint.

- **Root Cause:** The endpoint's first draft was written under the assumption that every repository class would expose a uniform `find_by_id(uuid)` / `find_by_identifier(value)` interface, mirroring `MachineRepository`. In reality, `ProductRepository` only had `find_by_identifier` (the dual-mode helper from Sprint 2.1) — `find_by_id` was never added because no other call site needed it. The method was assumed but never implemented.
- **Fix:** Per the user's directive ("Do NOT use any repository pattern. Query `supabase_admin.table()` directly"), rewrote the endpoint inline with six direct Supabase queries (machine, product, status log, warranty, active reservation, open issues). Each lookup is best-effort: if the table doesn't exist yet (future sprint) or the row simply isn't there, the field is returned as `null` / `[]` rather than 500-ing the whole response.

  ```python
  @router.get("/machines/{identifier}/full-detail")
  def full_detail(identifier: str, ...):
      machine = lookup_machine(identifier)
      if not machine: raise HTTPException(404, "Machine not found")
      product = supabase_admin.table("products").select("*").eq(
          "id", machine["product_id"]
      ).execute().data
      product = product[0] if product else None
      # ... best-effort lookups for warranty, reservation, issues, log
      return {"machine": machine, "product": product, ...}
  ```

- **Prevention:** Don't call repository methods that haven't been verified to exist. Two options going forward:
  1. **Direct queries** for endpoints that aggregate from many tables — the cost of a few extra `.execute()` calls is lower than the cost of a half-built abstraction.
  2. **Repository contracts** — if repos must expose a uniform interface, define an abstract base class (or Protocol) so the missing method is a type error, not a runtime AttributeError.
- **Files changed:**
  - `backend/app/routers/machine_lifecycle.py` (rewrite of `/full-detail`)
- **Related bugs:** None — root cause was the abstraction itself, not a recurring schema/data issue.

---

## Bug 3.4 — fpdf2 v2.5.2 `ln=True` deprecation warnings

- **Date:** 2026-04-25
- **Task:** 3.2 (warranty PDF certificates)
- **Severity:** Cosmetic
- **Symptom:** Generating a warranty certificate PDF emitted **46 deprecation warnings** to stderr:

  ```
  DeprecationWarning: The parameter "ln" is deprecated since v2.5.1.
  Instead of ln=1 use new_x=XPos.LMARGIN new_y=YPos.NEXT.
  ```

  The PDF rendered correctly, but the noise hid actual signal in the test output and would later fire on every customer-facing certificate download.

- **Root Cause:** fpdf2 v2.5.1 deprecated the boolean `ln=` parameter on `cell()` in favor of explicit `XPos`/`YPos` enums. The first draft of `_render_certificate_pdf` was written against pre-v2.5 examples and used `ln=True` everywhere.
- **Fix:** Defined two reusable kwargs dicts at the top of the router and passed them via `**` everywhere a line break was needed:

  ```python
  from fpdf.enums import XPos, YPos

  _NEXT_LINE = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
  _SAME_LINE = {"new_x": XPos.RIGHT,   "new_y": YPos.TOP}

  pdf.cell(0, 12, "ElixirX", align="C", **_NEXT_LINE)
  ```

  Also replaced `pdf.output(dest="S")` with the v2.5+ form `pdf.output()` and normalized the return type (modern fpdf2 returns `bytearray`; legacy `str`).

- **Prevention:** When pulling in a library version that's already several minor releases old, scan the changelog for deprecations before writing usage examples from memory. For PDF/imaging libraries specifically, treat warning-level output as a forcing function — they tend to flip from warnings to hard errors in the next major release.
- **Files changed:**
  - `backend/app/routers/warranty.py`
- **Related bugs:** None — purely a library-version mismatch.

---

## Bug 3.5 — `notifications` column name `read` vs `is_read`, plus `machine_id` non-existent

- **Date:** 2026-04-26
- **Task:** 3.3 / 3.4 / 3.5 (reservation/issue/warranty notification dispatch)
- **Severity:** Major
- **Symptom:** Reservation requests, issue reports, and expiring-warranty checks all appeared to succeed in tests — the primary action (reservation created, issue logged) returned 201/200 — but admins received zero notifications. There was no error visible in the logs because the notification-dispatch code was wrapped in `try/except: pass`.
- **Root Cause:** Two bugs hidden by the same try/except:
  1. The notification insert payload used `read: False`, but the actual column on the `notifications` table is `is_read`.
  2. The payload also included a `machine_id` field that doesn't exist on `notifications` (entity references go via `entity_type` + `entity_id` instead).

  Both errors raised `PostgrestAPIError` from Supabase, which the `try/except: pass` swallowed silently. The features looked working in manual testing but no admin ever got pinged.

- **Fix:** Probed the actual schema via a one-off insert (`{"user_id": "...", "title": "test", "message": "x", "type": "test"}` and inspecting the returned row) to learn the canonical column set. Then routed every caller through a single helper:

  ```python
  # backend/app/core/notification_helper.py
  def create_notification(
      *, user_id, title, message, notification_type,
      entity_type=None, entity_id=None,
  ):
      supabase_admin.table("notifications").insert({
          "user_id": user_id,
          "title": title,
          "message": message,
          "type": notification_type,
          "entity_type": entity_type,
          "entity_id": entity_id,
          "is_read": False,
          "created_at": datetime.now(timezone.utc).isoformat(),
      }).execute()

  def notify_admins(*, title, message, notification_type, ...):
      admins = supabase_admin.table("profiles").select("id").in_(
          "role", ["admin", "super_admin"]
      ).execute().data or []
      for a in admins:
          create_notification(user_id=a["id"], ...)
  ```

  All routers (reservations, issues, warranty) now call `notify_admins` / `notify_user` instead of writing inserts inline. The helper still wraps the call in try/except (notifications shouldn't break the primary flow) but it now raises into a logger instead of silently swallowing.

- **Prevention:** Two rules locked in after this:
  1. **Never silently swallow Postgrest errors.** `try/except: pass` on a database insert masks both schema mismatches and real outages. Log the exception even if the action is best-effort.
  2. **Schema before code.** When writing against a table for the first time, do a `select *` (or a probe insert) first to confirm column names, rather than guessing from another table's convention (`read` is intuitive but `is_read` is what's there).
- **Files changed:**
  - `backend/app/core/notification_helper.py` (new file)
  - `backend/app/routers/reservations.py`
  - `backend/app/routers/issues.py`
  - `backend/app/routers/warranty.py`
- **Related bugs:** [Bug 3.2](#bug-32--wrong-postgrest-embed-syntax-for-changed_by-profile-join) — same "code's column names disagree with the schema's column names" pattern.

---

## Bug 3.6 — 404 from warranty/reservation lookups treated as page errors

- **Date:** 2026-04-28
- **Task:** 3.6 (Machine Detail page)
- **Severity:** Major
- **Symptom:** Loading the Machine Detail page for a freshly registered machine showed a red error banner "Request failed (404)". The machine itself loaded fine — but the warranty card and reservation card, which call dedicated endpoints, both got 404 (because no warranty or reservation existed yet) and surfaced that as a fatal error.
- **Root Cause:** `apiGet` throws on any non-OK status. The Machine Detail page wrapped the warranty fetch in a `try/catch` that set the page-level `error` state on any failure, including the legitimate 404 case. The page was effectively unusable for any new machine until a warranty was created — exactly backwards from the intended UX.
- **Fix:** Added an `apiGetOptional<T>()` helper to `frontend/src/lib/api.ts` that returns `null` on 404 and throws on every other non-OK status:

  ```typescript
  export async function apiGetOptional<T>(endpoint: string): Promise<T | null> {
    const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, { method: 'GET' })
    if (res.status === 404) return null
    return handleResponse<T>(res)
  }
  ```

  MachineDetail.tsx then uses it for warranty, reservation, and issues — all three legitimately empty states for new machines:

  ```typescript
  try {
    const w = await apiGetOptional<Warranty>(`/api/warranty/machine/${id}`, token)
    setWarranty(w)  // null → "No warranty set" card
  } catch (e) {
    console.error('Warranty fetch error:', e)  // 500/network only
    setWarranty(null)
  }
  ```

  500s and network failures still log to the console and render the "no data" state — they don't crash the page, but they're not silently absorbed either.

- **Prevention:** Every backend endpoint that semantically means "lookup a record that may not exist yet" (warranty for a machine, reservation for a machine, profile by email) returns 404 for the missing case. The frontend must distinguish "404 = expected absence" from "500 = real failure" — `apiGetOptional` enforces this at the call-site so the distinction can't be forgotten.
- **Files changed:**
  - `frontend/src/lib/api.ts`
  - `frontend/src/pages/MachineDetail.tsx`
- **Related bugs:** [Bug 3.7 — Token expiry](#bug-37--invalid-or-expired-token-after-1-hour) — same conversation, both bugs were on the Machine Detail page.

---

## Bug 3.7 — "Invalid or expired token" after 1 hour

- **Date:** 2026-04-28
- **Task:** 3.6 (frontend auth)
- **Severity:** Major
- **Symptom:** Users left a tab open over lunch (~1 hour). On their next click, every API call returned:

  ```
  401 {"detail": "Invalid or expired token"}
  ```

  The page stopped working — every fetch failed — but the user was still rendered as "logged in" because no event triggered a re-auth. Manually reloading the page didn't help; the localStorage token was still expired. Only logging out and back in fixed it.

- **Root Cause:** Supabase access tokens expire after 1 hour. The original auth implementation only stored the access token in localStorage and replayed it on every request. There was no refresh-token flow, no `onAuthStateChange` listener, and no retry-on-401 path. Once the token expired, the app was effectively dead.
- **Fix:** A four-piece change that turned the Supabase JS SDK into a token cache the rest of the app reads from:

  1. **`frontend/src/lib/supabaseClient.ts` (new)** — a Supabase client configured with `persistSession: true` + `autoRefreshToken: true`. The SDK silently refreshes the access token in the background on a timer.

  2. **`frontend/src/lib/api.ts` — `fetchWithAuth`** — every authenticated call goes through this wrapper. It reads the current token from `supabase.auth.getSession()`, attempts the request, and on 401 calls `supabase.auth.refreshSession()` before retrying with the new token. If the refresh itself fails (refresh token revoked or also expired), it invokes a registered `onAuthFailure` handler:

     ```typescript
     async function fetchWithAuth(input: string, init: RequestInit = {}): Promise<Response> {
       const token = await getCurrentToken()
       const headers = new Headers(init.headers)
       if (token) headers.set('Authorization', `Bearer ${token}`)
       let res = await fetch(input, { ...init, headers })
       if (res.status === 401) {
         const { data: refreshed, error } = await supabase.auth.refreshSession()
         const newToken = refreshed?.session?.access_token
         if (error || !newToken) {
           onAuthFailure()
           throw new Error('Session expired')
         }
         headers.set('Authorization', `Bearer ${newToken}`)
         res = await fetch(input, { ...init, headers })
       }
       return res
     }
     ```

  3. **`frontend/src/lib/auth.tsx` — AuthProvider** — registers the redirect-to-login handler with `api.ts` on mount, hydrates the Supabase session from localStorage on page load (so `getSession()` works on the very first fetch), and listens for `onAuthStateChange` events to mirror `TOKEN_REFRESHED` back into React state and `SIGNED_OUT` into a navigation to `/login`.

  4. **`apiGet` / `apiPostAuth` / `apiPut` / `apiDelete` / `apiGetBlob`** — all rebuilt on top of `fetchWithAuth` so every authenticated call site automatically gets the refresh-and-retry behavior.

- **Prevention:** Treat the access token as a cache that can expire at any moment, not as a static credential. The refresh-on-401 wrapper must sit in the lowest possible layer (the fetch helper) so no individual call site has to remember to handle expiry. Code review red flag: any direct `fetch()` call in a page or component that includes an `Authorization` header — that's a bypass of the wrapper.
- **Files changed:**
  - `frontend/src/lib/supabaseClient.ts` (new)
  - `frontend/src/lib/api.ts`
  - `frontend/src/lib/auth.tsx`
- **Related bugs:** [Bug 3.8 — Raw `fetch()` bypassing the wrapper](#bug-38--raw-fetch-calls-bypassing-the-token-refresh-wrapper)

---

## Bug 3.8 — Raw `fetch()` calls bypassing the token refresh wrapper

- **Date:** 2026-04-30
- **Task:** 3.6 / 3.7 (Inventory page, StockModal)
- **Severity:** Major
- **Symptom:** After Bug 3.7 was "fixed," the warranty page and machine detail page worked perfectly across hour-long idle periods — but **registering a machine** (Inventory → Register Machine), **adding a flavor**, **adding a consumable product**, or **any batch operation in the StockModal** still showed "Invalid or expired token" after 1 hour. The fix was real but partial.
- **Root Cause:** The `fetchWithAuth` wrapper from Bug 3.7 only protects calls that go through the `apiGet` / `apiPostAuth` / `apiPut` / `apiDelete` helpers. **Nine call sites** across `Inventory.tsx` (3) and `StockModal.tsx` (6) still made raw `fetch()` calls with manually constructed `Authorization: Bearer ${access_token}` headers — these inherited the React state's stale token and never triggered the refresh path. The wrapper existed; these files just hadn't been migrated to use it.
- **Fix:** Converted every raw `fetch()` in `Inventory.tsx` and `StockModal.tsx` to the equivalent helper:

  | Before                                              | After                                                |
  |-----------------------------------------------------|------------------------------------------------------|
  | `fetch('${BASE}/api/supplement-flavors', {POST})`   | `apiPostAuth('/api/supplement-flavors', body, t)`    |
  | `fetch('${BASE}/api/products', {POST})`             | `apiPostAuth('/api/products', body, t)`              |
  | `fetch('${BASE}/api/machines', {POST})`             | `apiPostAuth('/api/machines', body, t)`              |
  | `fetch('${BASE}/api/consumable-batches?...', {GET})`| `apiGet('/api/consumable-batches?...', t)`           |
  | `fetch('${BASE}/api/consumable-batches', {POST})`   | `apiPostAuth('/api/consumable-batches', body, t)`    |
  | `fetch('${BASE}/api/consumable-batches/{id}/ship', {POST})` | `apiPostAuth('.../ship', body, t)`           |
  | `fetch('${BASE}/api/consumable-batches/{id}', {PUT})`  | `apiPut('/api/consumable-batches/{id}', body, t)` |
  | `fetch('${BASE}/api/consumable-batches/{id}', {DEL})`  | `apiDelete('/api/consumable-batches/{id}', t)`    |
  | `fetch('${BASE}/api/consumable-stock/{id}', {PUT})`    | `apiPut('/api/consumable-stock/{id}', body, t)`   |

  Removed the now-unused `BASE_URL = import.meta.env.VITE_API_URL` constants from both files. Verified with a project-wide grep that the only remaining `fetch()` calls are inside `lib/api.ts` itself (where they belong — that file is what the wrapper is built on).

- **Prevention:** When introducing a wrapper that's meant to be the canonical entry point (auth, caching, telemetry), do a project-wide audit to convert all existing call sites in the **same** PR. Leaving "I'll migrate the rest later" comments creates exactly this hidden-bypass class of bug. Code review check: `grep -rn 'await fetch\|= fetch' frontend/src` — anything outside `lib/api.ts` should be challenged.
- **Files changed:**
  - `frontend/src/pages/Inventory.tsx` (3 fetches removed)
  - `frontend/src/components/inventory/StockModal.tsx` (6 fetches removed)
- **Related bugs:** [Bug 3.7 — Token expiry](#bug-37--invalid-or-expired-token-after-1-hour) — this is the partial-coverage tail of the same fix.

---

## Bug 3.9 — Cross-router static priority for `/machines/status-summary`

- **Date:** 2026-04-22
- **Task:** 3.1 (lifecycle endpoints registered in `main.py`)
- **Severity:** Minor
- **Symptom:** `GET /api/machines/status-summary` returned 400:

  ```
  {"code": "22P02", "message": "invalid input syntax for type uuid: \"status-summary\""}
  ```

  The same error pattern as Bug 2.2 — but on a path the new lifecycle router was supposed to own.

- **Root Cause:** Sprint 2's `inventory_router` defines `GET /api/machines/{machine_id}` as a dynamic route. When `machine_lifecycle_router` was registered with `app.include_router(inventory_router); app.include_router(machine_lifecycle_router)`, FastAPI walks routes in registration order — so the dynamic `/machines/{machine_id}` from inventory swallowed `/machines/status-summary` from lifecycle and tried to resolve `"status-summary"` as a UUID.

  This is the same "static before dynamic" issue as Sprint 2 Bug 2.8, but **across routers** instead of within one — the per-router fix from 2.8 didn't help because the conflict was at the `app.include_router()` ordering layer.

- **Fix:** Reordered router registration in `main.py` so the lifecycle router (with its static paths) is included **before** `inventory_router`:

  ```python
  # main.py — registration order matters
  app.include_router(machine_lifecycle_router)  # /machines/status-summary, /machines/bulk-status
  app.include_router(warranty_router)           # /warranty/dashboard, /warranty/check-expiring
  app.include_router(reservations_router)       # /reservations/expiring-soon, /reservations/by-account
  app.include_router(inventory_router)          # must come last — owns /machines/{machine_id}
  ```

  Added a comment documenting the rule. Updated CLAUDE.md to call out the cross-router case explicitly so it's caught at design time, not at the first 400.

- **Prevention:** When two routers share a path prefix and one of them owns a `{param}` route at that prefix, the static-route router must be registered first. Better yet, give static endpoints a more specific sub-prefix (`/machine-stats/summary`, `/machine-actions/bulk-status`) so the collision is impossible by construction. Documented in CLAUDE.md alongside the within-router rule from Sprint 2.
- **Files changed:**
  - `backend/app/main.py`
  - `CLAUDE.md` (added cross-router note under "Core Conventions")
- **Related bugs:** Sprint 2 [Bug 2.8](sprint-2.md) — within-router version of the same rule.

---

## Common Patterns

### Schema drift — code references columns or tables that don't exist

Three Sprint 3 bugs (3.1, 3.2, 3.5) had the same root cause: the code assumed a schema shape that didn't match the database. In each case the fix took longer than the bug warranted because the failure was either silent (3.5 — try/except swallow) or a generic Postgrest error (3.1 — PGRST205, 3.2 — relationship not found).

- **Symptom:** PGRST205 "Could not find the table", "Could not find a relationship", silently zero notifications written.
- **Fix:** Run the migration before merging code that depends on it. Probe the actual schema (`select *` or a one-row insert with full payload echo) before writing the first insert against a new table. Use exact column names, not intuited ones (`is_read`, not `read`).
- **Prevention:** Treat the database schema as the source of truth and the code as the consumer, not the other way around. Never wrap a database mutation in `try/except: pass` — log the exception, even if the action is best-effort.
- **See:** Bug 3.1, Bug 3.2, Bug 3.5

---

### Wrapper coverage — when introducing a canonical helper, migrate all call sites in the same PR

Bug 3.7 introduced `fetchWithAuth` as the single token-refresh path. Bug 3.8 was the **partial-coverage** tail: nine raw `fetch()` calls in `Inventory.tsx` / `StockModal.tsx` continued to bypass it for two more days, and the bug looked exactly like the one 3.7 supposedly fixed.

- **Symptom:** A bug that's "fixed" still reproduces on certain pages.
- **Fix:** Project-wide grep for the old API surface as part of the same PR. Convert every call site, then verify with `grep -rn 'await fetch' frontend/src` that the only remaining matches are inside the wrapper file itself.
- **Prevention:** When the goal of a PR is "all calls go through X," the success criterion is **zero direct calls to the underlying primitive** — not "X exists and is used in the example file." Bake the grep into the PR description as a verification step.
- **See:** Bug 3.7, Bug 3.8

---

### 404 ergonomics — distinguish "no record yet" from "real failure"

Endpoints that lookup-by-key for an entity that may not exist yet (warranty for a machine, reservation for a machine) return 404 by HTTP convention. The frontend must treat that 404 as a successful absence, not as an error to surface.

- **Symptom:** A red error banner appears on a page that's actually working — the user just hasn't created the related record yet.
- **Fix:** Add an `apiGetOptional<T>()` helper that returns `null` on 404 and throws on any other non-OK status. Use it everywhere the absence of a record is part of the normal lifecycle.
- **Prevention:** When designing a `GET /resource/lookup-key/{key}` endpoint, decide whether 404 is a normal state. If yes, document it on the route and add a test that verifies the frontend handles it gracefully.
- **See:** Bug 3.6

---

### Cross-router static priority — applies to `app.include_router()` ordering, not just within-router declarations

Sprint 2 established the rule "static before dynamic within a router." Sprint 3 extended it: when two routers share a path prefix and one owns a `{param}` route at that prefix, the static-route router must be `include_router`'d first.

- **Symptom:** A literal path returns the same UUID-parse error you'd get from passing a non-UUID to a dynamic route — but the route is in a different router.
- **Fix:** Either reorder the `include_router` calls so static-route routers come first, or give static endpoints a more specific sub-prefix that can't collide.
- **Prevention:** When adding a new router, list every prefix it overlaps with and verify the `include_router` order. Better: design URL prefixes to be non-overlapping by construction.
- **See:** Bug 3.9, Sprint 2 Bug 2.8

---

## Sprint 3 Summary

| Severity | Count |
|----------|-------|
| **Total bugs** | 9 |
| Blocker | 2 |
| Major | 5 |
| Minor | 1 |
| Cosmetic | 1 |

**Themes:**
- **3 schema-drift bugs** (3.1 missing table, 3.2 wrong embed/column, 3.5 wrong column name + silent swallow) — all rooted in code disagreeing with the actual database. Fixed by probing the live schema and routing notification writes through one helper.
- **2 frontend-auth bugs** (3.6 404-as-error, 3.7 token expiry, 3.8 wrapper bypass — counted as 2 themes since 3.6 is a separate UX issue) — all touched on the same lib/api.ts surface. Net result: every authenticated call now refreshes silently and 404s are first-class "no data" responses.
- **1 abstraction bug** (3.3 missing repository method) — root cause was the abstraction itself; the fix was to drop it for endpoints that aggregate from many tables.
- **1 routing bug** (3.9) — extension of Sprint 2's static-before-dynamic rule to cross-router ordering. Captured in CLAUDE.md.
- **1 library bug** (3.4 fpdf2 deprecations) — caught at warning level, fixed before they became errors.

**Comparison to Sprint 2:**
- Sprint 2 was dominated by a single root cause repeated across resources (UUID vs friendly identifier, 3 of 9 bugs).
- Sprint 3 was more diverse: 4 distinct themes, with the schema/database alignment cluster as the biggest source.
- The frontend auth refactor was the most expensive bug to fully resolve (3.7 + 3.8 spanned ~3 days end-to-end), but resulted in a stable wrapper that should pay dividends for the rest of the project.
