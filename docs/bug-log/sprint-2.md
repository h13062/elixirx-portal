# Sprint 2 — Bug Log

Sprint 2 covers the inventory module: products, machines, consumable stock, supplement flavor tracking, batch/lot management, and the inventory page UI. Bugs in this sprint cluster around three themes: **friendly-identifier ergonomics** (UUID vs SKU/name/serial), **incremental scope expansion** (simple stock → flavors → batches), and **CRUD completeness** (Create/Read shipped before Update/Delete).

---

## Bug 2.1 — "Invalid input syntax for type uuid" when registering machines

- **Date:** 2026-04-14
- **Task:** 2.1 (inventory backend endpoints)
- **Severity:** Major
- **Symptom:** When testing `POST /api/machines`, the user had to look up a product's UUID in Supabase and paste it into the request body. Any other value (the SKU like `RX-PRO`, or the friendly name `RX Pro`) returned a Postgres error:

  ```
  {'code': '22P02', 'message': 'invalid input syntax for type uuid: "RX-PRO"'}
  ```

  Same error appeared on every endpoint that took a `product_id` query parameter or path parameter — there was no way to reference a product without its raw UUID.

- **Root Cause:** The original `POST /api/machines` handler (and the `consumable-stock` handlers) passed the incoming `product_id` string straight into a `.eq("id", payload.product_id)` filter. The `products.id` column is a `UUID`, so Postgres rejected anything that didn't parse as a UUID before it could even attempt the lookup. The API was technically correct but the UX assumed the client already knew internal database IDs — unrealistic for an admin pasting values from a spec sheet or SKU label.
- **Fix:** Added a `lookup_product()` helper that accepts a UUID **or** a SKU **or** a case-insensitive name, and resolves it to the canonical `products.id` UUID before any further query:

  ```python
  def is_uuid(value: str) -> bool:
      try:
          uuid.UUID(value)
          return True
      except ValueError:
          return False

  def lookup_product(identifier: str):
      if is_uuid(identifier):
          result = supabase_admin.table("products").select("*").eq("id", identifier).execute()
      else:
          result = supabase_admin.table("products").select("*").eq("sku", identifier).execute()
          if not result.data:
              result = supabase_admin.table("products").select("*").ilike("name", identifier).execute()
      return result.data[0] if result.data else None
  ```

  Every endpoint that takes a product reference now calls `lookup_product()` first, then uses the resolved UUID for downstream queries. This pattern was later extracted into `ProductRepository.find_by_identifier()` during the Sprint 2.4 OOP refactor.

- **Prevention:** Any path/query/body parameter that semantically refers to a "product" or "user" or "machine" must accept the human-friendly identifier the operator actually has on hand (SKU, serial, email), and resolve internally to the UUID. Treat raw UUIDs as an internal artifact — never require them at the API boundary.
- **Files changed:**
  - `backend/app/routers/inventory_router.py`
  - Later refactored into `backend/app/repositories/product_repository.py`
- **Related bugs:** [Bug 2.2 — `GET /api/machines/{machine_id}` rejected serial numbers](#bug-22--get-apimachinesmachine_id-rejected-serial-numbers), [Bug 2.3 — Same UUID issue on consumable stock](#bug-23--same-uuid-only-issue-on-consumable-stock-and-other-product-references)

---

## Bug 2.2 — `GET /api/machines/{machine_id}` rejected serial numbers

- **Date:** 2026-04-14
- **Task:** 2.1 (inventory backend endpoints)
- **Severity:** Major
- **Symptom:** Looking up a machine by its serial number (e.g., `RX-2026-001`) returned 400:

  ```
  GET /api/machines/RX-2026-001
  → 400 Bad Request
  {'code': '22P02', 'message': 'invalid input syntax for type uuid: "RX-2026-001"'}
  ```

  Operators in the field always have the serial number printed on the unit — they do not have the database UUID.

- **Root Cause:** The handler did `.eq("id", machine_id)` directly. The `machines.id` column is a UUID, so any non-UUID path parameter was rejected at the Postgres layer. Same root-cause class as Bug 2.1, but on the `machines` table — `serial_number` is the natural human key but the API only honored UUIDs.
- **Fix:** Added a `lookup_machine()` helper symmetric to `lookup_product()` — UUID or `serial_number`:

  ```python
  def lookup_machine(identifier: str):
      if is_uuid(identifier):
          result = (supabase_admin.table("machines")
                    .select("*, products(name, sku)")
                    .eq("id", identifier).execute())
      else:
          result = (supabase_admin.table("machines")
                    .select("*, products(name, sku)")
                    .eq("serial_number", identifier).execute())
      return result.data[0] if result.data else None
  ```

  `GET /api/machines/{machine_id}` now resolves `machine_id` through this helper. Updated the route comment to make the dual-mode behavior explicit:

  ```python
  # GET /api/machines/{machine_id}  — accepts UUID or serial_number
  ```

- **Prevention:** Whenever a domain object has a unique human-readable key (serial number, SKU, email, slug), endpoints that accept that object's identifier must accept either form. Document this in the route docstring/comment so the dual-mode behavior is discoverable.
- **Files changed:**
  - `backend/app/routers/inventory_router.py`
  - Later refactored into `backend/app/repositories/machine_repository.py`
- **Related bugs:** [Bug 2.1](#bug-21--invalid-input-syntax-for-type-uuid-when-registering-machines), [Bug 2.3](#bug-23--same-uuid-only-issue-on-consumable-stock-and-other-product-references)

---

## Bug 2.3 — Same UUID-only issue on consumable stock and other product references

- **Date:** 2026-04-14
- **Task:** 2.1 (inventory backend endpoints)
- **Severity:** Major
- **Symptom:** Bugs 2.1 and 2.2 were the visible tip — the same class of failure appeared on every endpoint that touched a product:

  ```
  GET /api/consumable-stock/SUPP-PACK         → 400 invalid uuid
  PUT /api/consumable-stock/SUPP-PACK         → 400 invalid uuid
  POST /api/machines  body={"product_id":"RX Pro", ...}  → 400 invalid uuid
  ```

  Each endpoint had been written independently with its own raw `.eq("id", ...)` query.

- **Root Cause:** No shared lookup abstraction existed. Each handler reimplemented "find a product by ID" inline with the same UUID-only assumption. As more endpoints were added, the bug surface grew linearly with endpoint count.
- **Fix:** Applied the friendly-identifier pattern across **every** product-referencing endpoint in `inventory_router.py`:

  - `GET /api/consumable-stock/{product_id}` — accepts UUID, SKU, or name
  - `PUT /api/consumable-stock/{product_id}` — accepts UUID, SKU, or name
  - `POST /api/machines` — `payload.product_id` accepts UUID, SKU, or name
  - All resolve through `lookup_product()` and use the canonical UUID downstream.

  In Sprint 2.4 this was hardened by extracting the lookup into `ProductRepository.find_by_identifier()` so no future endpoint can forget the pattern.

- **Prevention:** Identifier resolution belongs in the repository layer, not in route handlers. If you find yourself writing `.eq("id", incoming_value)` against a UUID column inside a router, stop — that lookup must go through a `find_by_identifier()` style helper. Code review checklist item: "Does this endpoint accept the user-friendly form of the ID?"
- **Files changed:**
  - `backend/app/routers/inventory_router.py`
  - `backend/app/repositories/product_repository.py` (Sprint 2.4 refactor — added `find_by_identifier`)
  - `backend/app/repositories/machine_repository.py` (Sprint 2.4 refactor)
- **Related bugs:** [Bug 2.1](#bug-21--invalid-input-syntax-for-type-uuid-when-registering-machines), [Bug 2.2](#bug-22--get-apimachinesmachine_id-rejected-serial-numbers)

---

## Bug 2.4 — Consumable stock update UI was too hard to find

- **Date:** 2026-04-23
- **Task:** 2.4 (consumable stock management redesign)
- **Severity:** Major
- **Symptom:** Once Sprint 2.2 / 2.3 shipped the inventory page, the only way to adjust consumable stock was a small inline ✏️ pencil button beside each card's quantity. During internal testing nobody could find it without being told where to look — the affordance was visually buried, the click target was tiny, and it gave no indication that more actions (low-stock alerts, batch history) were even possible. Admins ended up editing rows directly in Supabase rather than using the portal.
- **Root Cause:** UX, not a code defect. The card was treated as a passive read-only display with edit-as-an-afterthought. As the stock model grew (thresholds, alerts, batch history, flavor-level breakdown coming in Bug 2.5), the inline editor had no room to host the new controls — every new field would have made the card more cluttered without making the primary action more discoverable.
- **Fix:** Redesigned the consumable stock UX around a dedicated **Stock Management Modal** triggered by clicking the card itself (not a hidden icon):

  - Each `ConsumableStock` card got `class="stock-card-clickable"` and an `onClick` handler. Hover state highlights the border so the affordance is visible.
  - A new `StockModal.tsx` component (~790 lines) hosts the full management surface: header (name, SKU, description, price), 4-stat summary bar (manufactured / in-stock / shipped / batches), low-stock banner, flavor tabs (for the supplement pack), batch table with inline ship/edit/delete, add-batch form, and alert settings (threshold + enabled toggle).
  - Removed all inline edit state from `Inventory.tsx` (`editingStockId`, `editingQuantity`, `stockSaving`, `stockError`) — the modal owns the full edit lifecycle now.
  - Added a "Manage Batches" button as a secondary affordance for users who don't realize the card is clickable.

- **Prevention:** When a card or row carries non-trivial actions (more than view + edit-one-field), promote interactivity to the whole tile and use a dedicated modal/panel. Don't keep stacking icon buttons. Rule of thumb: if the third action you want to add doesn't fit comfortably in the existing surface, the surface needs to grow, not shrink the controls.
- **Files changed:**
  - `frontend/src/components/inventory/StockModal.tsx` (new)
  - `frontend/src/components/inventory/StockModal.css` (new)
  - `frontend/src/pages/Inventory.tsx` (removed inline-edit state, wired modal open/close)
  - `frontend/src/pages/Inventory.css` (added `.stock-card-clickable`, `.stock-section-header`, etc.)
- **Related bugs:** [Bug 2.5](#bug-25--supplement-tracking-was-too-simplistic-no-flavors-no-batches)

---

## Bug 2.5 — Supplement tracking was too simplistic (no flavors, no batches)

- **Date:** 2026-04-23
- **Task:** 2.4 (consumable stock + batch tracking + flavor management)
- **Severity:** Major
- **Symptom:** The original consumable stock model treated "Supplement Pack" as a single row with a single `quantity` integer. In reality:

  - Supplement Pack ships in multiple flavors (Berry, Citrus, Tropical, etc.) — each with its own SKU, price, and physical inventory. The system could not tell flavors apart.
  - Each manufactured run has a batch number, a manufacture date, and an expiry date. For a consumable health product these fields are mandatory for traceability (recall scope, expiry tracking, regulatory reporting). The system stored none of it.
  - Every shipment to a customer needs to be tied back to a specific batch (so a recall touches only the affected lot, not all stock). The system tracked total quantity but not which batch it was being drawn from.

  The first sales call where someone asked "which flavor is in stock?" exposed the gap immediately.

- **Root Cause:** Sprint 2.1's data model was scoped for a generic consumable: one row per product in `consumable_stock` with a single `quantity` column. That worked for non-flavored items but had no extension point for variant-level inventory or lot-level traceability. It was a correct model for the wrong product shape.
- **Fix:** Major redesign across the data model, backend, and UI:

  **Data model:**
  - Each supplement flavor became a row in `supplement_flavors` with its own SKU, description, default price, sort order, and `is_active` flag (soft-delete).
  - New `consumable_batches` table: `(id, product_id, flavor_id NULL, batch_number, quantity_manufactured, quantity, quantity_shipped, manufacture_date, expiry_date, shipped_date, shipped_to, status, notes)`.
  - `consumable_stock.quantity` is no longer a free-form integer — it is recalculated as `SUM(consumable_batches.quantity)` after every batch insert/update/delete/ship. The stock row becomes a derived aggregate, not a source of truth.

  **Backend (new endpoints):**
  - `GET/POST/PUT/DELETE /api/supplement-flavors`
  - `GET/POST/PUT/DELETE /api/consumable-batches` (with `product_id` and `flavor_id` filters)
  - `POST /api/consumable-batches/{batch_id}/ship` — decrements `quantity`, increments `quantity_shipped`, sets status (`in_stock` / `partially_shipped` / `fully_shipped`).
  - `GET /api/consumable-batches/report` — summary + by-flavor breakdown.
  - `_recalculate_stock(product_id)` helper called from every batch mutation:

    ```python
    def _recalculate_stock(self, product_id: str) -> None:
        total = self._batches.sum_quantity_for_product(product_id)
        self._stock.recalculate_from_batches(product_id, total, self._now_iso())
    ```

  - Validation: `flavor_id` is **required** for supplement-pack batches and **forbidden** for non-supplement products:

    ```python
    is_supplement = "supplement" in product["name"].lower()
    if is_supplement and not payload.flavor_id:
        raise HTTPException(400, "flavor_id is required for Supplement Pack batches")
    if not is_supplement and payload.flavor_id:
        raise HTTPException(400, "flavor_id must not be provided for non-supplement products")
    ```

  **Frontend:**
  - Flavor cards row below the Supplement Pack card — each clickable, shows total in stock, batch count, price.
  - Stock Management Modal gained flavor tabs (only shown when the modal is opened on the supplement main card), filtering the batch table by flavor_id.
  - Add-batch form requires a flavor selection for supplement; hidden for non-supplement products.

- **Prevention:** Before locking in a stock model, ask three questions: (1) Does this product have variants? (2) Does it need lot-level traceability? (3) Are individual shipments traceable back to a specific manufacturing run? If the answer to any is yes, the data model must include variants and batches from day one — retrofitting them later means changing the meaning of `quantity` (now derived, not authoritative) and rewriting every endpoint that touched it.
- **Files changed:**
  - `backend/app/models/inventory_models.py`
  - `backend/app/repositories/supplement_flavor_repository.py` (new)
  - `backend/app/repositories/batch_repository.py` (new)
  - `backend/app/repositories/product_repository.py`
  - `backend/app/repositories/stock_repository.py`
  - `backend/app/services/inventory_service.py`
  - `backend/app/routers/inventory_router.py`
  - `frontend/src/components/inventory/types.ts`
  - `frontend/src/components/inventory/StockModal.tsx`
  - `frontend/src/components/inventory/StockModal.css`
  - `frontend/src/pages/Inventory.tsx`
  - `frontend/src/pages/Inventory.css`
  - Schema SQL: new `supplement_flavors` and `consumable_batches` tables
- **Related bugs:** [Bug 2.4](#bug-24--consumable-stock-update-ui-was-too-hard-to-find), [Bug 2.6](#bug-26--no-way-to-add-new-products-or-flavors-from-the-portal), [Bug 2.7](#bug-27--no-edit-or-delete-for-products-flavors-or-batches)

---

## Bug 2.6 — No way to add new products or flavors from the portal

- **Date:** 2026-04-23
- **Task:** 2.4 (consumable stock + flavor management)
- **Severity:** Major
- **Symptom:** The inventory page could only display whatever rows had been pre-seeded into `products` and `supplement_flavors` via SQL. To add a new flavor (e.g., "Vanilla") or a new consumable (e.g., "Cleaning Cartridge"), an admin had to open Supabase and write the INSERT by hand, including generating a UUID and remembering the foreign-key relationships. Reps could not onboard new SKUs without engineering involvement.
- **Root Cause:** Sprint 2.1 only implemented `GET` for products and supplement flavors. `POST/PUT/DELETE` were deferred and then forgotten in the rush to ship the inventory UI. The endpoints existed in spirit (the spec called for them) but never made it into the router.
- **Fix:** Added the missing creation endpoints and matching UI affordances:

  - `POST /api/supplement-flavors` (admin only) — creates a flavor with SKU uniqueness check.
  - `POST /api/products` (admin only) — creates a consumable or machine product. If `category='consumable'`, auto-creates the `consumable_stock` row with `quantity=0` so the new product immediately shows up on the inventory page.
  - **UI:** "+ Add Flavor" dashed card at the end of the flavor row opens a small modal. "+ Add New Consumable Product" text button in the consumable stock section header opens an inline form with name, SKU, default price, and description fields.

- **Prevention:** When implementing CRUD endpoints, ship the full set (Create + Read + Update + Delete) before declaring the resource done. "We'll add Create later" almost always means "an admin will edit Postgres directly for six weeks." Treat partial CRUD as an open ticket, not a milestone.
- **Files changed:**
  - `backend/app/models/inventory_models.py` (added `ProductCreate`, `SupplementFlavorCreate`)
  - `backend/app/repositories/product_repository.py` (added `create`, `sku_exists`)
  - `backend/app/repositories/supplement_flavor_repository.py` (new — full CRUD)
  - `backend/app/repositories/stock_repository.py` (added `create` to seed stock row)
  - `backend/app/services/inventory_service.py` (`create_product`, `create_supplement_flavor`)
  - `backend/app/routers/inventory_router.py`
  - `frontend/src/pages/Inventory.tsx` (Add Flavor modal, Add Product inline form)
  - `frontend/src/pages/Inventory.css`
- **Related bugs:** [Bug 2.5](#bug-25--supplement-tracking-was-too-simplistic-no-flavors-no-batches), [Bug 2.7](#bug-27--no-edit-or-delete-for-products-flavors-or-batches)

---

## Bug 2.7 — No edit or delete for products, flavors, or batches

- **Date:** 2026-04-23
- **Task:** 2.4 (consumable stock management)
- **Severity:** Major
- **Symptom:** After Bug 2.6 was fixed (Create endpoints added), only Create + Read existed. There was no way to:

  - Rename a flavor (typo in "Citrus" → "Citrius")
  - Update a product's default price
  - Correct a batch's quantity after a miscount
  - Discontinue a flavor (without deleting historical batch references)
  - Delete a duplicate batch entered by mistake

  Every edit required a Supabase round-trip again — same operational burden Bug 2.6 was supposed to eliminate.

- **Root Cause:** Same pattern as Bug 2.6 — Update and Delete were deferred. Treating CRUD as "Create and Read first, U/D later" repeatedly produced gaps where the backend technically supported the data model but the day-to-day workflow required out-of-band SQL.
- **Fix:** Added `PUT` and `DELETE` endpoints for every resource in the inventory module, with the appropriate semantics for each:

  - `PUT /api/products/{product_id}` (admin only) — partial update via `ProductUpdate` (`name`, `sku`, `default_price`, `description`, `is_active`).
  - `PUT /api/supplement-flavors/{flavor_id}` (admin only) — partial update including `is_active`.
  - `DELETE /api/supplement-flavors/{flavor_id}` (admin only) — **soft delete** (sets `is_active=false`). Hard delete would orphan historical batch rows.
  - `PUT /api/consumable-batches/{batch_id}` (admin only) — adjust quantity, batch number, expiry, notes. Triggers `_recalculate_stock()`.
  - `DELETE /api/consumable-batches/{batch_id}` (admin only) — hard delete (a typo'd batch should leave no trace). Also triggers `_recalculate_stock()`.
  - **UI:** Inline edit and delete-confirmation rows inside the Stock Management Modal's batch table. Permission-checked via `isAdmin` flag — non-admins only see the read view.

  Soft-delete vs hard-delete decision: soft-delete for entities referenced by historical records (flavors, products), hard-delete only for entities that are pure "did this ever exist" data (mistaken batch entries before any shipment).

- **Prevention:** When designing a resource, decide up front: does deleting it break referential integrity in historical records? If yes → soft delete with `is_active`. If no → hard delete. Document the choice on each endpoint so it's not relitigated. And: **do not ship a Create endpoint without the matching Update and Delete in the same PR** — half-CRUD is a tax that compounds.
- **Files changed:**
  - `backend/app/models/inventory_models.py` (added `ProductUpdate`, `SupplementFlavorUpdate`, `BatchUpdate`)
  - `backend/app/repositories/product_repository.py` (`update`)
  - `backend/app/repositories/supplement_flavor_repository.py` (`update`, `soft_delete`)
  - `backend/app/repositories/batch_repository.py` (`update`, `delete`)
  - `backend/app/services/inventory_service.py`
  - `backend/app/routers/inventory_router.py`
  - `frontend/src/components/inventory/StockModal.tsx` (inline edit/delete rows, confirmation flow)
  - `frontend/src/components/inventory/StockModal.css`
- **Related bugs:** [Bug 2.5](#bug-25--supplement-tracking-was-too-simplistic-no-flavors-no-batches), [Bug 2.6](#bug-26--no-way-to-add-new-products-or-flavors-from-the-portal)

---

## Bug 2.8 — `GET /api/consumable-batches/report` matched as a `{batch_id}`

- **Date:** 2026-04-23
- **Task:** 2.4 (batch report endpoint)
- **Severity:** Minor
- **Symptom:** The first call to `GET /api/consumable-batches/report` returned 404:

  ```
  GET /api/consumable-batches/report
  → 404 {"detail":"Batch not found"}
  ```

  The endpoint itself was implemented and registered — yet it never ran.

- **Root Cause:** FastAPI matches routes in the order they are registered on the router. `GET /api/consumable-batches/{batch_id}` had been declared first, so the literal string `report` was being captured as the `batch_id` path parameter. The dynamic route swallowed the static one.
- **Fix:** Re-ordered the route declarations so all static paths come before any path-parameterized route on the same prefix:

  ```python
  # Static — registered FIRST
  @router.get("/consumable-batches/report")
  def batch_report(...): ...

  # Dynamic — registered AFTER
  @router.get("/consumable-batches/{batch_id}")
  def get_batch(batch_id: str, ...): ...

  @router.post("/consumable-batches/{batch_id}/ship")
  def ship_batch(...): ...
  ```

- **Prevention:** When defining a router with mixed static + path-parameter routes under the same prefix, always declare static paths first. A safer alternative: nest the static endpoints under a more specific sub-prefix (e.g., `/consumable-batches-reports/summary`) so collisions are impossible. Linter check candidate.
- **Files changed:**
  - `backend/app/routers/inventory_router.py`
- **Related bugs:** —

---

## Bug 2.9 — `React.FormEvent` deprecation warning in React 19

- **Date:** 2026-04-23
- **Task:** 2.4 (Add Flavor / Add Product forms in `Inventory.tsx`)
- **Severity:** Minor
- **Symptom:** TypeScript warning (hint 6385) on `handleAddFlavor` and `handleAddProduct`:

  ```
  'React.FormEvent' is deprecated.
  ```

  Compilation still succeeded but the editor showed the strikethrough.

- **Root Cause:** React 19 deprecated the legacy `React.FormEvent<T>` synthetic-event type alias in favor of the underlying DOM event type. The rest of the file had already been migrated to a structural type (`{ preventDefault(): void }`) for `handleSubmit`, but the two new handlers added in this task still used the old name.
- **Fix:** Replaced the deprecated type with the same structural form already used elsewhere in the file:

  ```tsx
  // Before
  const handleAddFlavor = async (e: React.FormEvent) => { ... }

  // After
  const handleAddFlavor = async (e: { preventDefault(): void }) => { ... }
  ```

- **Prevention:** When adding a new handler, copy the signature from an existing handler in the same file rather than reaching for the framework alias from memory. The structural type also doesn't lock the function to a specific synthetic-event class — it works equally well from a button click that fakes the same shape.
- **Files changed:**
  - `frontend/src/pages/Inventory.tsx`
- **Related bugs:** —

---

## Common Patterns

These are the recurring issue classes from Sprint 2. Check here before debugging similar problems in future sprints.

### UUID vs Friendly Identifier pattern

Endpoints that take an entity identifier in a path, query, or body field must accept the human-friendly form (SKU, serial number, name, email) as well as the canonical UUID — and resolve to the UUID internally before any DB query.

- **Symptom:** `invalid input syntax for type uuid: "<friendly value>"` from Postgres.
- **Fix:** Implement a `find_by_identifier(identifier: str)` method on the repository that tries UUID → SKU → name (case-insensitive). Route handlers call this helper instead of doing `.eq("id", incoming_value)` directly.
- **Prevention:** Treat raw UUIDs as internal artifacts. Operators have SKUs and serial numbers in hand; they never have UUIDs. Code review: every `.eq("id", <route param>)` against a UUID column is a bug.
- **See:** Bug 2.1, Bug 2.2, Bug 2.3

---

### Simple tracking vs Batch tracking pattern

For any consumable, regulated, or perishable product, the stock model must include lot-level (batch) tracking from day one — not retrofitted later.

- **Symptom:** "Which flavor is in stock?" / "Which batch did this shipment come from?" / "What expires next month?" — none of these can be answered with a single `quantity` integer per product.
- **Fix:** Three-table model: `products` (catalog) → `consumable_stock` (derived aggregate, `quantity = SUM(batches.quantity)`) → `consumable_batches` (source of truth, with manufacture_date, expiry_date, batch_number, shipped_date). Recalculate the aggregate on every batch mutation.
- **Prevention:** Before locking a stock model, ask: variants? lot traceability? shipment-to-batch link? If yes to any, build the batch model up front. Retrofitting it changes the meaning of every `quantity` field already in the codebase.
- **See:** Bug 2.5

---

### Always implement full CRUD pattern

Ship Create + Read + Update + Delete in the same PR, not "Create now, edit later." Half-CRUD pushes operators into the database to do basic admin work.

- **Symptom:** Admins editing rows in Supabase to fix a typo, change a price, or remove a duplicate. New entities can be created from the UI but never modified.
- **Fix:** For every new resource, design all four verbs at once. Decide soft-delete vs hard-delete based on whether historical references exist. Build the UI affordances (edit row, delete confirmation) alongside the backend endpoints.
- **Prevention:** PR review checklist: "Does this resource have all four CRUD operations? If not, why is U/D deferred — and is there a ticket?" Treat partial CRUD as a known operational tax with a ticking cost.
- **See:** Bug 2.6, Bug 2.7

---

### Feature requests during implementation pattern

A feature spec written before the first user demo will miss product-shape constraints (variants, lots, regulatory fields) that are obvious the moment a real stakeholder asks "but what about X?"

- **Symptom:** Inventory shipped with a single supplement quantity, then the next call asked about flavors, then the call after that asked about expiry tracking. Each gap required a redesign of the same data model.
- **Fix:** During spec review for a domain object, walk through its physical/regulatory lifecycle: how does it get manufactured, packaged, shipped, returned, recalled, expired? Any answer that touches data not in the model is a missing field.
- **Prevention:** Run a "lifecycle stress test" on the model before implementation: list every state the entity can be in and every event that moves it between states. If a state or event has no data home, the model is incomplete.
- **See:** Bug 2.5, Bug 2.6, Bug 2.7

---

### FastAPI route ordering — static before dynamic

Within a router, static path segments must be declared before path-parameter routes that share the same prefix, or the dynamic route will swallow the static one.

- **Symptom:** A literal path like `/foo/report` returns "not found" with a message that came from the `/foo/{id}` handler.
- **Fix:** Re-order route declarations: all static paths before any `{param}` path on the same prefix. Or use a more specific sub-prefix for static endpoints to avoid the collision.
- **Prevention:** When mixing static and parameterized routes, group statics at the top of the router file with a comment marking the boundary. Lint candidate: detect overlapping route patterns.
- **See:** Bug 2.8

---

## Sprint 2 Summary

| Severity | Count |
|----------|-------|
| **Total bugs** | 9 |
| Blocker | 0 |
| Major | 7 |
| Minor | 2 |
| Cosmetic | 0 |

**Themes:**
- 3 bugs (2.1–2.3) on the same UUID-vs-friendly-identifier root cause — resolved with a single repository-level `find_by_identifier` pattern.
- 3 bugs (2.5–2.7) from the inventory model expanding mid-sprint (single quantity → flavors → batches → full CRUD).
- 1 UX bug (2.4) where a buried inline editor was promoted to a clickable card + dedicated modal.
- 2 minor bugs (2.8 route ordering, 2.9 React 19 deprecation) — surface-level mistakes caught quickly.

No blockers in this sprint — every issue had a workaround (raw UUID, direct Supabase edits) while the proper fix was being built.
