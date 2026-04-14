# Sprint 1 — Bug Log

Sprint 1 covers authentication, database schema setup, and the backend foundation (FastAPI, Supabase client, auth endpoints).

---

## Bug 1.1 — "Unsafe use of new enum value" when running schema SQL

- **Date:** 2026-03-10
- **Task:** 1.1 (database schema)
- **Severity:** Blocker
- **Symptom:** Running the full schema SQL in the Supabase SQL Editor produced:

  ```
  ERROR: unsafe use of new enum value "super_admin"
  DETAIL: New enum values must be committed before they can be used.
  ```

- **Root Cause:** PostgreSQL requires that `ALTER TYPE ... ADD VALUE` is committed as its own transaction before any subsequent DDL (like `CREATE TABLE`) can reference the new enum value. When both statements run in the same script (same transaction block), the new value isn't yet visible to the parser handling the `CREATE TABLE`.
- **Fix:** Split the SQL into two separate queries in the Supabase SQL Editor. Run and commit the `ALTER TYPE` first, then run the `CREATE TABLE` that uses the enum:

  ```sql
  -- Query 1 — run this first and let it commit
  ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'super_admin';

  -- Query 2 — run this after query 1 completes
  CREATE TABLE profiles (
    ...
    role user_role NOT NULL DEFAULT 'rep',
    ...
  );
  ```

- **Prevention:** Whenever adding a new value to an existing enum, always run the `ALTER TYPE` as a standalone statement before any DDL that references it. Never batch them in the same script.
- **Files changed:** Schema SQL (Supabase SQL Editor)
- **Related bugs:** —

---

## Bug 1.2 — "Could not find the table 'public.system_config'"

- **Date:** 2026-03-10
- **Task:** 1.2 (Supabase client setup)
- **Severity:** Blocker
- **Symptom:** FastAPI startup or a request triggered:

  ```
  Could not find the table 'public.system_config' in the schema cache
  ```

- **Root Cause:** The Python backend referenced `supabase.table("system_config")` but the `system_config` table had not yet been created in Supabase. The schema cache doesn't know about tables that don't exist.
- **Fix:** Create the missing table in the Supabase SQL Editor:

  ```sql
  CREATE TABLE system_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
  );
  ```

- **Prevention:** Always create the full DB schema before writing Python code that references it. Keep a `schema.sql` file in the repository so the intended schema is always documented and reproducible.
- **Files changed:** Schema SQL (Supabase SQL Editor)
- **Related bugs:** [Bug 1.3 — "Could not find table 'public.admin_log'"](#bug-13----could-not-find-table-publicadmin_log)

---

## Bug 1.3 — "Could not find the table 'public.admin_log'"

- **Date:** 2026-03-10
- **Task:** 1.2 (Supabase client setup)
- **Severity:** Blocker
- **Symptom:**

  ```
  Could not find the table 'public.admin_log' in the schema cache
  ```

- **Root Cause:** Same pattern as Bug 1.2 — code referenced a table before it existed in the database.
- **Fix:** Create the table:

  ```sql
  CREATE TABLE admin_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event TEXT,
    actor_id UUID,
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```

- **Prevention:** See Bug 1.2. Same class of error.
- **Files changed:** Schema SQL (Supabase SQL Editor)
- **Related bugs:** [Bug 1.2 — "Could not find the table 'public.system_config'"](#bug-12----could-not-find-the-table-publicsystem_config), [Bug 1.4 — Missing column 'event' in admin_log](#bug-14----missing-column-event-in-admin_log)

---

## Bug 1.4 — Missing column 'event' in admin_log

- **Date:** 2026-03-10
- **Task:** 1.2 (Supabase client setup)
- **Severity:** Major
- **Symptom:** Inserting into `admin_log` failed with:

  ```
  column "event" of relation "admin_log" does not exist
  ```

- **Root Cause:** The `admin_log` table was created without an `event` column (the initial `CREATE TABLE` was minimal), but the Python backend's insert payload included `event`.
- **Fix:**

  ```sql
  ALTER TABLE admin_log ADD COLUMN event TEXT;
  ```

- **Prevention:** Before writing backend code that inserts into a table, verify the table's column list in Supabase matches what the code expects. Maintain a canonical `schema.sql` in the repo.
- **Files changed:** Schema SQL (Supabase SQL Editor)
- **Related bugs:** [Bug 1.3](#bug-13----could-not-find-table-publicadmin_log)

---

## Bug 1.5 — PGRST116 "Cannot coerce the result to a single JSON object"

- **Date:** 2026-03-12
- **Task:** 1.4 (login endpoint)
- **Severity:** Blocker
- **Symptom:** Any endpoint that used `.single()` on a Supabase query would crash when the query returned zero rows:

  ```
  {'code': 'PGRST116', 'details': 'The result contains 0 rows', 'hint': None,
   'message': 'JSON object requested, multiple (or no) rows returned'}
  ```

- **Root Cause:** Supabase's `.single()` method is only safe when the query is guaranteed to return exactly one row. If zero rows are returned (e.g., user not found, token expired), it raises an exception instead of returning `None` or an empty result.
- **Fix:** Replace every `.single()` call throughout the codebase with `.execute()`, then check `result.data` manually:

  ```python
  # Before (fragile)
  result = supabase.table("profiles").select("*").eq("id", user_id).single()

  # After (safe)
  result = supabase.table("profiles").select("*").eq("id", user_id).execute()
  if not result.data:
      raise HTTPException(status_code=404, detail="User not found")
  row = result.data[0]
  ```

- **Prevention:** Never use `.single()`. Project-wide convention: always use `.execute()` with an explicit length check. This is documented in the Common Patterns section of this log.
- **Files changed:**
  - `backend/app/routers/auth_router.py`
  - `backend/app/routers/inventory_router.py`
- **Related bugs:** —

---

## Bug 1.6 — "Database error creating new user" from Supabase Auth

- **Date:** 2026-03-14
- **Task:** 1.6 (invite rep endpoint)
- **Severity:** Blocker
- **Symptom:** Calling `supabase.auth.admin.create_user()` returned a generic Supabase error:

  ```
  AuthApiError: Database error creating new user
  ```

  No further detail was provided by Supabase.

- **Root Cause:** A `handle_new_user` trigger on `auth.users` was firing on insert and failing — likely because the trigger tried to insert a row into `public.profiles` with columns or constraints that didn't match the current schema. Supabase wraps trigger failures in this generic auth error, hiding the real cause.
- **Fix:** Disabled the `handle_new_user` trigger in Supabase:

  ```sql
  DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
  ```

  Profile creation is now handled explicitly in Python immediately after the `create_user()` call succeeds:

  ```python
  auth_resp = supabase_admin.auth.admin.create_user({...})
  new_user_id = auth_resp.user.id
  supabase_admin.table("profiles").insert({
      "id": new_user_id,
      "email": email,
      "role": role,
      ...
  }).execute()
  ```

- **Prevention:** Avoid using Supabase database triggers for critical user-facing flows. Trigger failures are opaque and hard to debug. Keep the logic in Python where errors surface with full stack traces.
- **Files changed:**
  - `backend/app/routers/auth_router.py`
  - Schema SQL (trigger removal in Supabase SQL Editor)
- **Related bugs:** —

---

## Bug 1.7 — RLS policy violation on invitations table (403)

- **Date:** 2026-03-14
- **Task:** 1.6 (invite rep endpoint)
- **Severity:** Blocker
- **Symptom:** Backend insert into the `invitations` table returned 403:

  ```
  {'code': '42501', 'details': None, 'hint': None,
   'message': 'new row violates row-level security policy for table "invitations"'}
  ```

- **Root Cause:** Row Level Security was enabled on the `invitations` table with a policy like `auth.uid() = created_by`. When called from the FastAPI backend using the `service_role` key, `auth.uid()` is always `null` — there is no authenticated user in the JWT context. The RLS policy therefore rejected every insert from the backend, even though the `service_role` key is supposed to bypass RLS.

  The issue was that RLS bypass requires the Supabase client to be initialized with the service role key *and* `auth` set to service role. The original client wasn't fully configured this way.

- **Fix:** Disabled RLS on the `invitations` table entirely:

  ```sql
  ALTER TABLE invitations DISABLE ROW LEVEL SECURITY;
  ```

  The `invitations` table is only ever written to by the backend (never directly by the frontend), so RLS provides no additional security here — the `service_role` key already restricts access.

- **Prevention:** Only enable RLS on tables that are accessed directly by frontend clients using user JWTs. For backend-only tables (invitations, admin_log, system_config), RLS is redundant when the backend uses `service_role` and adds maintenance overhead.
- **Files changed:** Schema SQL (Supabase SQL Editor)
- **Related bugs:** [Bug 1.8 — Auth client contamination](#bug-18----user-not-allowed-403-on-admin-calls-auth-client-contamination)

---

## Bug 1.8 — "User not allowed" 403 on admin calls — auth client contamination

- **Date:** 2026-03-15
- **Task:** 1.7 (direct rep account creation)
- **Severity:** Blocker
- **Symptom:** `supabase.auth.admin.create_user()` returned 403:

  ```
  AuthApiError: User not allowed
  ```

  This happened even though the Supabase client was initialized with the `service_role` key.

- **Root Cause:** The same Supabase client instance was used for both regular user-authenticated requests (which call `supabase.auth.set_session(token)` or similar) and admin operations (`supabase.auth.admin.*`). User token calls contaminated the internal auth state of the shared client instance. When the admin call was then made, the client sent the user's JWT instead of the service role key, and Supabase rejected it.
- **Fix:** Created a dedicated `supabase_admin` client in `backend/app/core/supabase_client.py` that is initialized once with the service role key and never has its auth state modified by user requests:

  ```python
  # supabase_client.py
  from supabase import create_client

  # User-facing client — auth state may be set per-request
  supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

  # Admin client — service role only, never touched by user auth flows
  supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
  ```

  All `auth.admin.*` calls and backend-only DB writes use `supabase_admin` exclusively.

- **Prevention:** Always maintain two separate Supabase client instances: one for user-context operations, one for admin/service-role operations. Never share a single client between the two. Document this as an architectural constraint in the codebase.
- **Files changed:**
  - `backend/app/core/supabase_client.py`
  - `backend/app/routers/auth_router.py`
  - `backend/app/routers/inventory_router.py`
- **Related bugs:** [Bug 1.7 — RLS policy violation](#bug-17----rls-policy-violation-on-invitations-table-403)

---

## Bug 1.9 — Supabase invite emails not sending

- **Date:** 2026-03-15
- **Task:** 1.6 (invite rep endpoint)
- **Severity:** Major
- **Symptom:** `supabase.auth.admin.invite_user_by_email()` returned success but the recipient never received an email. Intermittently worked in testing but was unreliable.
- **Root Cause:** Supabase's free tier uses a shared email service with strict rate limits and low deliverability. Invite emails are deprioritized and frequently dropped or delayed by hours. This is a known limitation of the Supabase free tier, not a code bug.
- **Fix / Decision:** Abandoned Supabase's email system entirely for this project. The flow was redesigned:
  1. Admin creates the rep account directly via `supabase_admin.auth.admin.create_user()` with an auto-generated temporary password.
  2. Admin copies and shares the temporary password out-of-band (e.g., via Slack/SMS).
  3. Rep logs in with the temp password and is prompted to change it on first login.
  4. Resend (transactional email service) will be integrated in Sprint 11 for proper invite email delivery.
- **Prevention:** Do not rely on Supabase's built-in email delivery for any user-facing flow. Use a dedicated transactional email service (Resend, SendGrid, Postmark) from the start.
- **Files changed:**
  - `backend/app/routers/auth_router.py` (removed invite flow, added direct creation)
- **Related bugs:** —

---
