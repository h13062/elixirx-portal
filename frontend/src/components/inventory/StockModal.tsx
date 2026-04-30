import { useState, useEffect, useCallback, useMemo } from 'react'
import { X, Pencil, Trash2, Package } from 'lucide-react'
import './StockModal.css'
import type { ConsumableStock, ConsumableBatch, SupplementFlavor } from './types'
import { apiGet, apiPostAuth, apiPut, apiDelete } from '../../lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StockModalProps {
  product: ConsumableStock
  flavor: SupplementFlavor | null
  flavors: SupplementFlavor[]
  accessToken: string
  isAdmin: boolean
  onClose: () => void
  onStockUpdated: () => void
}

interface AddBatchForm {
  batch_number: string
  quantity_manufactured: string
  manufacture_date: string
  expiry_date: string
  flavor_id: string
  notes: string
}

interface ShipForm {
  quantity_to_ship: string
  shipped_date: string
  shipped_to: string
}

const BLANK_ADD: AddBatchForm = {
  batch_number: '',
  quantity_manufactured: '',
  manufacture_date: '',
  expiry_date: '',
  flavor_id: '',
  notes: '',
}

const BLANK_SHIP: ShipForm = {
  quantity_to_ship: '',
  shipped_date: '',
  shipped_to: '',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusBadgeClass(s: string): string {
  if (s === 'in_stock') return 'sm-badge sm-badge-green'
  if (s === 'partially_shipped') return 'sm-badge sm-badge-amber'
  return 'sm-badge sm-badge-gray'
}

function statusLabel(s: string): string {
  if (s === 'in_stock') return 'In Stock'
  if (s === 'partially_shipped') return 'Partial'
  if (s === 'fully_shipped') return 'Shipped'
  return s
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function StockModal({
  product,
  flavor,
  flavors,
  accessToken,
  isAdmin,
  onClose,
  onStockUpdated,
}: StockModalProps) {
  const isSupplementMain = !flavor && product.product_name.toLowerCase().includes('supplement')

  // ── Batch data ──
  const [batches, setBatches] = useState<ConsumableBatch[]>([])
  const [batchesLoading, setBatchesLoading] = useState(true)
  const [flavorTab, setFlavorTab] = useState<string | null>(flavor?.id ?? null)

  // ── Add batch ──
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState<AddBatchForm>({ ...BLANK_ADD, flavor_id: flavor?.id ?? '' })
  const [addSaving, setAddSaving] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  // ── Ship batch ──
  const [shippingId, setShippingId] = useState<string | null>(null)
  const [shipForm, setShipForm] = useState<ShipForm>(BLANK_SHIP)
  const [shipSaving, setShipSaving] = useState(false)
  const [shipError, setShipError] = useState<string | null>(null)

  // ── Edit batch ──
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editNotes, setEditNotes] = useState('')
  const [editExpiry, setEditExpiry] = useState('')
  const [editBatchNum, setEditBatchNum] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // ── Delete batch ──
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deleteSaving, setDeleteSaving] = useState(false)

  // ── Alert settings ──
  const [alertThreshold, setAlertThreshold] = useState(
    product.min_threshold != null ? String(product.min_threshold) : ''
  )
  const [alertEnabled, setAlertEnabled] = useState(product.alert_enabled ?? false)
  const [alertSaving, setAlertSaving] = useState(false)
  const [alertMsg, setAlertMsg] = useState<string | null>(null)

  // ── Toast ──
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)

  function showToast(msg: string, ok = true) {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  // ── Fetch batches ──
  const fetchBatches = useCallback(async () => {
    setBatchesLoading(true)
    try {
      const params = new URLSearchParams({ product_id: product.product_id })
      const data = await apiGet<ConsumableBatch[]>(
        `/api/consumable-batches?${params}`,
        accessToken,
      )
      setBatches(data)
    } catch {
      // Keep empty
    } finally {
      setBatchesLoading(false)
    }
  }, [accessToken, product.product_id])

  useEffect(() => {
    fetchBatches()
  }, [fetchBatches])

  // ── Filtered batches by tab ──
  const filteredBatches = useMemo(() => {
    if (!flavorTab) return batches
    return batches.filter(b => b.flavor_id === flavorTab)
  }, [batches, flavorTab])

  // ── Summary ──
  const summary = useMemo(() => ({
    manufactured: filteredBatches.reduce((s, b) => s + b.quantity_manufactured, 0),
    in_stock:     filteredBatches.reduce((s, b) => s + b.quantity, 0),
    shipped:      filteredBatches.reduce((s, b) => s + b.quantity_shipped, 0),
    count:        filteredBatches.length,
  }), [filteredBatches])

  // ── Add batch ──
  async function handleAddBatch(e: React.FormEvent) {
    e.preventDefault()
    if (!addForm.batch_number.trim()) { setAddError('Batch number is required'); return }
    if (!addForm.quantity_manufactured || Number(addForm.quantity_manufactured) <= 0) {
      setAddError('Quantity must be > 0'); return
    }
    if (!addForm.manufacture_date) { setAddError('Manufacture date is required'); return }

    setAddSaving(true)
    setAddError(null)
    try {
      const body: Record<string, unknown> = {
        product_id: product.product_id,
        batch_number: addForm.batch_number.trim(),
        quantity_manufactured: Number(addForm.quantity_manufactured),
        manufacture_date: addForm.manufacture_date,
      }
      if (addForm.flavor_id) body.flavor_id = addForm.flavor_id
      if (addForm.expiry_date) body.expiry_date = addForm.expiry_date
      if (addForm.notes.trim()) body.notes = addForm.notes.trim()

      await apiPostAuth('/api/consumable-batches', body, accessToken)
      setAddForm({ ...BLANK_ADD, flavor_id: flavor?.id ?? '' })
      setShowAdd(false)
      await fetchBatches()
      onStockUpdated()
      showToast('Batch added successfully')
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add batch')
    } finally {
      setAddSaving(false)
    }
  }

  // ── Ship batch ──
  async function handleShip(batchId: string) {
    if (!shipForm.quantity_to_ship || Number(shipForm.quantity_to_ship) <= 0) {
      setShipError('Quantity must be > 0'); return
    }
    if (!shipForm.shipped_date) { setShipError('Shipped date is required'); return }
    if (!shipForm.shipped_to.trim()) { setShipError('Shipped to is required'); return }

    setShipSaving(true)
    setShipError(null)
    try {
      await apiPostAuth(
        `/api/consumable-batches/${batchId}/ship`,
        {
          quantity_to_ship: Number(shipForm.quantity_to_ship),
          shipped_date: shipForm.shipped_date,
          shipped_to: shipForm.shipped_to.trim(),
        },
        accessToken,
      )
      setShippingId(null)
      setShipForm(BLANK_SHIP)
      await fetchBatches()
      onStockUpdated()
      showToast('Batch shipped successfully')
    } catch (err) {
      setShipError(err instanceof Error ? err.message : 'Failed to ship batch')
    } finally {
      setShipSaving(false)
    }
  }

  // ── Edit batch ──
  function startEdit(b: ConsumableBatch) {
    setEditingId(b.id)
    setEditBatchNum(b.batch_number)
    setEditNotes(b.notes ?? '')
    setEditExpiry(b.expiry_date ?? '')
    setEditError(null)
  }

  async function saveEdit(batchId: string) {
    setEditSaving(true)
    setEditError(null)
    try {
      const body: Record<string, unknown> = {
        batch_number: editBatchNum.trim() || undefined,
        notes: editNotes || undefined,
        expiry_date: editExpiry || undefined,
      }
      await apiPut(`/api/consumable-batches/${batchId}`, body, accessToken)
      setEditingId(null)
      await fetchBatches()
      showToast('Batch updated')
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to update batch')
    } finally {
      setEditSaving(false)
    }
  }

  // ── Delete batch ──
  async function handleDelete(batchId: string) {
    setDeleteSaving(true)
    try {
      await apiDelete(`/api/consumable-batches/${batchId}`, accessToken)
      setConfirmDeleteId(null)
      await fetchBatches()
      onStockUpdated()
      showToast('Batch deleted')
    } catch {
      showToast('Failed to delete batch', false)
    } finally {
      setDeleteSaving(false)
    }
  }

  // ── Alert settings ──
  async function saveAlert() {
    setAlertSaving(true)
    setAlertMsg(null)
    try {
      const body: Record<string, unknown> = { alert_enabled: alertEnabled }
      if (alertThreshold !== '') body.min_threshold = Number(alertThreshold)
      await apiPut(`/api/consumable-stock/${product.product_id}`, body, accessToken)
      onStockUpdated()
      setAlertMsg('Saved')
      setTimeout(() => setAlertMsg(null), 2000)
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : 'Error')
    } finally {
      setAlertSaving(false)
    }
  }

  const lowStock = product.min_threshold != null && product.quantity < product.min_threshold

  return (
    <div className="sm-overlay" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="sm-container" role="dialog" aria-modal="true">

        {/* ── Header ── */}
        <div className="sm-header">
          <div className="sm-header-info">
            <div className="sm-header-title-row">
              <h2 className="sm-title">
                {flavor ? flavor.name : product.product_name}
                {flavor && (
                  <span className="sm-title-sub"> · {product.product_name}</span>
                )}
              </h2>
              <button className="sm-close-btn" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            {(flavor?.sku || product.product_sku) && (
              <p className="sm-sku">
                {flavor ? flavor.sku : product.product_sku}
              </p>
            )}
            {(flavor?.description || product.description) && (
              <p className="sm-description">
                {flavor ? flavor.description : product.description}
              </p>
            )}
            <p className="sm-price">
              ${((flavor?.default_price ?? product.default_price) ?? 0).toFixed(2)}
            </p>
          </div>
        </div>

        {/* ── Summary bar ── */}
        <div className="sm-summary-bar">
          <div className="sm-stat sm-stat-blue">
            <span className="sm-stat-value">{summary.manufactured}</span>
            <span className="sm-stat-label">Manufactured</span>
          </div>
          <div className="sm-stat sm-stat-green">
            <span className="sm-stat-value">{summary.in_stock}</span>
            <span className="sm-stat-label">In Stock</span>
          </div>
          <div className="sm-stat sm-stat-amber">
            <span className="sm-stat-value">{summary.shipped}</span>
            <span className="sm-stat-label">Shipped</span>
          </div>
          <div className="sm-stat sm-stat-purple">
            <span className="sm-stat-value">{summary.count}</span>
            <span className="sm-stat-label">Batches</span>
          </div>
        </div>

        {/* ── Low stock warning ── */}
        {lowStock && (
          <div className="sm-low-stock-banner">
            Low Stock: {product.quantity} units remaining
            {product.min_threshold != null && ` (threshold: ${product.min_threshold})`}
          </div>
        )}

        {/* ── Flavor tabs (supplement main card only) ── */}
        {isSupplementMain && flavors.length > 0 && (
          <div className="sm-tabs">
            <button
              className={`sm-tab${flavorTab === null ? ' sm-tab-active' : ''}`}
              onClick={() => setFlavorTab(null)}
            >
              All
            </button>
            {flavors.map(f => (
              <button
                key={f.id}
                className={`sm-tab${flavorTab === f.id ? ' sm-tab-active' : ''}`}
                onClick={() => setFlavorTab(f.id)}
              >
                {f.name}
              </button>
            ))}
          </div>
        )}

        {/* ── Batch table ── */}
        <div className="sm-table-wrap">
          {batchesLoading ? (
            <div className="sm-loading">Loading batches…</div>
          ) : filteredBatches.length === 0 ? (
            <div className="sm-empty">
              <Package size={32} className="sm-empty-icon" />
              <p>No batches yet. Add your first batch below.</p>
            </div>
          ) : (
            <table className="sm-table">
              <thead>
                <tr>
                  <th>Batch / Lot #</th>
                  {isSupplementMain && !flavorTab && <th>Flavor</th>}
                  <th className="sm-th-num">Mfg Qty</th>
                  <th className="sm-th-num">In Stock</th>
                  <th className="sm-th-num">Shipped</th>
                  <th>Mfg Date</th>
                  <th>Expiry</th>
                  <th>Status</th>
                  {isAdmin && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {filteredBatches.map(b => (
                  <>
                    <tr key={b.id} className={editingId === b.id ? 'sm-row-editing' : ''}>
                      <td className="sm-mono">
                        {editingId === b.id ? (
                          <input
                            className="sm-inline-input sm-mono"
                            value={editBatchNum}
                            onChange={e => setEditBatchNum(e.target.value)}
                          />
                        ) : b.batch_number}
                      </td>
                      {isSupplementMain && !flavorTab && (
                        <td className="sm-text-dim">{b.flavor_name ?? '—'}</td>
                      )}
                      <td className="sm-th-num">{b.quantity_manufactured}</td>
                      <td className="sm-th-num">{b.quantity}</td>
                      <td className="sm-th-num">{b.quantity_shipped}</td>
                      <td>{formatDate(b.manufacture_date)}</td>
                      <td>
                        {editingId === b.id ? (
                          <input
                            type="date"
                            className="sm-inline-input"
                            value={editExpiry}
                            onChange={e => setEditExpiry(e.target.value)}
                          />
                        ) : formatDate(b.expiry_date)}
                      </td>
                      <td><span className={statusBadgeClass(b.status)}>{statusLabel(b.status)}</span></td>
                      {isAdmin && (
                        <td>
                          <div className="sm-action-btns">
                            {editingId === b.id ? (
                              <>
                                <button
                                  className="sm-btn-save"
                                  onClick={() => saveEdit(b.id)}
                                  disabled={editSaving}
                                >
                                  {editSaving ? '…' : 'Save'}
                                </button>
                                <button
                                  className="sm-btn-cancel-sm"
                                  onClick={() => setEditingId(null)}
                                  disabled={editSaving}
                                >
                                  Cancel
                                </button>
                              </>
                            ) : (
                              <>
                                {b.status !== 'fully_shipped' && (
                                  <button
                                    className="sm-btn-ship"
                                    onClick={() => {
                                      setShippingId(shippingId === b.id ? null : b.id)
                                      setShipForm(BLANK_SHIP)
                                      setShipError(null)
                                    }}
                                    title="Ship"
                                  >
                                    Ship
                                  </button>
                                )}
                                <button
                                  className="sm-btn-icon"
                                  onClick={() => startEdit(b)}
                                  title="Edit"
                                >
                                  <Pencil size={13} />
                                </button>
                                <button
                                  className="sm-btn-icon sm-btn-danger"
                                  onClick={() => setConfirmDeleteId(b.id)}
                                  title="Delete"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </>
                            )}
                          </div>
                          {editingId === b.id && editError && (
                            <p className="sm-row-error">{editError}</p>
                          )}
                        </td>
                      )}
                    </tr>

                    {/* Edit notes row */}
                    {editingId === b.id && (
                      <tr className="sm-row-sub" key={`${b.id}-edit`}>
                        <td colSpan={isSupplementMain && !flavorTab ? 9 : 8}>
                          <div className="sm-notes-edit">
                            <label className="sm-notes-label">Notes</label>
                            <input
                              className="sm-inline-input sm-notes-input"
                              placeholder="Notes…"
                              value={editNotes}
                              onChange={e => setEditNotes(e.target.value)}
                            />
                          </div>
                        </td>
                      </tr>
                    )}

                    {/* Ship row */}
                    {shippingId === b.id && (
                      <tr className="sm-row-sub" key={`${b.id}-ship`}>
                        <td colSpan={isSupplementMain && !flavorTab ? 9 : 8}>
                          <div className="sm-ship-form">
                            <div className="sm-ship-fields">
                              <div className="sm-ship-field">
                                <label className="sm-field-label">Qty to ship</label>
                                <input
                                  type="number"
                                  className="sm-inline-input no-spinner sm-mono"
                                  min={1}
                                  max={b.quantity}
                                  placeholder={`max ${b.quantity}`}
                                  value={shipForm.quantity_to_ship}
                                  onChange={e => setShipForm(f => ({ ...f, quantity_to_ship: e.target.value }))}
                                />
                              </div>
                              <div className="sm-ship-field">
                                <label className="sm-field-label">Ship date</label>
                                <input
                                  type="date"
                                  className="sm-inline-input"
                                  value={shipForm.shipped_date}
                                  onChange={e => setShipForm(f => ({ ...f, shipped_date: e.target.value }))}
                                />
                              </div>
                              <div className="sm-ship-field sm-ship-field-wide">
                                <label className="sm-field-label">Shipped to</label>
                                <input
                                  className="sm-inline-input"
                                  placeholder="Distributor / Rep name…"
                                  value={shipForm.shipped_to}
                                  onChange={e => setShipForm(f => ({ ...f, shipped_to: e.target.value }))}
                                />
                              </div>
                            </div>
                            <div className="sm-ship-actions">
                              <button
                                className="sm-btn-confirm-ship"
                                onClick={() => handleShip(b.id)}
                                disabled={shipSaving}
                              >
                                {shipSaving ? 'Shipping…' : 'Confirm Ship'}
                              </button>
                              <button
                                className="sm-btn-cancel-sm"
                                onClick={() => { setShippingId(null); setShipError(null) }}
                                disabled={shipSaving}
                              >
                                Cancel
                              </button>
                            </div>
                            {shipError && <p className="sm-row-error">{shipError}</p>}
                          </div>
                        </td>
                      </tr>
                    )}

                    {/* Delete confirm row */}
                    {confirmDeleteId === b.id && (
                      <tr className="sm-row-sub sm-row-danger" key={`${b.id}-del`}>
                        <td colSpan={isSupplementMain && !flavorTab ? 9 : 8}>
                          <div className="sm-delete-confirm">
                            <span>Delete batch <strong className="sm-mono">{b.batch_number}</strong>? This cannot be undone.</span>
                            <button
                              className="sm-btn-delete-confirm"
                              onClick={() => handleDelete(b.id)}
                              disabled={deleteSaving}
                            >
                              {deleteSaving ? 'Deleting…' : 'Delete'}
                            </button>
                            <button
                              className="sm-btn-cancel-sm"
                              onClick={() => setConfirmDeleteId(null)}
                              disabled={deleteSaving}
                            >
                              Cancel
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* ── Add batch form ── */}
        {isAdmin && (
          <div className="sm-add-section">
            {!showAdd ? (
              <button className="sm-add-toggle" onClick={() => setShowAdd(true)}>
                + Add New Batch
              </button>
            ) : (
              <form className="sm-add-form" onSubmit={handleAddBatch} noValidate>
                <p className="sm-add-title">Add New Batch</p>
                <div className="sm-add-grid">
                  <div className="sm-add-field">
                    <label className="sm-field-label">Batch / Lot #</label>
                    <input
                      className="sm-inline-input sm-mono"
                      placeholder="LOT-XX-2026-001"
                      value={addForm.batch_number}
                      onChange={e => setAddForm(f => ({ ...f, batch_number: e.target.value }))}
                      disabled={addSaving}
                    />
                  </div>
                  <div className="sm-add-field">
                    <label className="sm-field-label">Qty Manufactured</label>
                    <input
                      type="number"
                      className="sm-inline-input no-spinner"
                      min={1}
                      placeholder="0"
                      value={addForm.quantity_manufactured}
                      onChange={e => setAddForm(f => ({ ...f, quantity_manufactured: e.target.value }))}
                      disabled={addSaving}
                    />
                  </div>
                  <div className="sm-add-field">
                    <label className="sm-field-label">Manufacture Date</label>
                    <input
                      type="date"
                      className="sm-inline-input"
                      value={addForm.manufacture_date}
                      onChange={e => setAddForm(f => ({ ...f, manufacture_date: e.target.value }))}
                      disabled={addSaving}
                    />
                  </div>
                  <div className="sm-add-field">
                    <label className="sm-field-label">Expiry Date <span className="sm-optional">(opt)</span></label>
                    <input
                      type="date"
                      className="sm-inline-input"
                      value={addForm.expiry_date}
                      onChange={e => setAddForm(f => ({ ...f, expiry_date: e.target.value }))}
                      disabled={addSaving}
                    />
                  </div>
                  {isSupplementMain && (
                    <div className="sm-add-field sm-add-field-full">
                      <label className="sm-field-label">Flavor</label>
                      <select
                        className="sm-inline-input"
                        value={addForm.flavor_id}
                        onChange={e => setAddForm(f => ({ ...f, flavor_id: e.target.value }))}
                        disabled={addSaving}
                      >
                        <option value="">Select flavor…</option>
                        {flavors.map(f => (
                          <option key={f.id} value={f.id}>{f.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="sm-add-field sm-add-field-full">
                    <label className="sm-field-label">Notes <span className="sm-optional">(opt)</span></label>
                    <input
                      className="sm-inline-input"
                      placeholder="Any notes…"
                      value={addForm.notes}
                      onChange={e => setAddForm(f => ({ ...f, notes: e.target.value }))}
                      disabled={addSaving}
                    />
                  </div>
                </div>
                {addError && <p className="sm-row-error sm-add-error">{addError}</p>}
                <div className="sm-add-actions">
                  <button type="submit" className="sm-btn-add" disabled={addSaving}>
                    {addSaving ? 'Adding…' : 'Add Batch'}
                  </button>
                  <button
                    type="button"
                    className="sm-btn-cancel-sm"
                    onClick={() => { setShowAdd(false); setAddError(null) }}
                    disabled={addSaving}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        )}

        {/* ── Alert settings ── */}
        {isAdmin && (
          <div className="sm-alert-section">
            <div className="sm-alert-row">
              <span className="sm-alert-label">Low Stock Alert</span>
              <div className="sm-alert-controls">
                <label className="sm-field-label">Threshold</label>
                <input
                  type="number"
                  className="sm-inline-input no-spinner sm-threshold-input"
                  min={0}
                  placeholder="—"
                  value={alertThreshold}
                  onChange={e => setAlertThreshold(e.target.value)}
                  disabled={alertSaving}
                />
                <label className="sm-toggle-wrap">
                  <input
                    type="checkbox"
                    className="sm-toggle-cb"
                    checked={alertEnabled}
                    onChange={e => setAlertEnabled(e.target.checked)}
                    disabled={alertSaving}
                  />
                  <span className="sm-toggle-label">{alertEnabled ? 'On' : 'Off'}</span>
                </label>
                <button className="sm-btn-alert-save" onClick={saveAlert} disabled={alertSaving}>
                  {alertSaving ? 'Saving…' : 'Save'}
                </button>
                {alertMsg && (
                  <span className={`sm-alert-msg${alertMsg === 'Saved' ? ' sm-alert-ok' : ' sm-alert-err'}`}>
                    {alertMsg}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Footer ── */}
        <div className="sm-footer">
          <button className="sm-btn-close-footer" onClick={onClose}>Close</button>
        </div>

        {/* ── Toast ── */}
        {toast && (
          <div className={`sm-toast${toast.ok ? ' sm-toast-ok' : ' sm-toast-err'}`}>
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  )
}
