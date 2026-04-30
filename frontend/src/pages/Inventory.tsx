import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import './Inventory.css'
import '../components/inventory/ConsumableStockSection.css'
import { useAuth } from '../lib/auth'
import { apiGet, apiDelete, apiPut, apiPostAuth } from '../lib/api'
import FilterBar from '../components/inventory/FilterBar'
import MachineTable from '../components/inventory/MachineTable'
import StockModal from '../components/inventory/StockModal'
import { X, Loader2, Plus, Package, Filter as FilterIcon, Beaker, Trash2, Pencil, CalendarCheck } from 'lucide-react'
import ConfirmModal from '../components/ConfirmModal'
import ReserveMachineModal from '../components/reservations/ReserveMachineModal'
import ReservationsTab from '../components/reservations/ReservationsTab'
import type {
  Machine,
  ConsumableStock,
  Product,
  SupplementFlavor,
  StatusFilter,
  TypeFilter,
  StatusCounts,
} from '../components/inventory/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FormData {
  serial_number: string
  product_id: string
  batch_number: string
  manufacture_date: string
  notes: string
}

interface FormErrors {
  serial_number?: string
  product_id?: string
  batch_number?: string
  manufacture_date?: string
}

interface Toast {
  message: string
  type: 'success' | 'error'
}

interface AddFlavorForm {
  name: string
  sku: string
  description: string
  default_price: string
  sort_order: string
}

interface AddProductForm {
  name: string
  sku: string
  description: string
  default_price: string
}

const BLANK_FORM: FormData = {
  serial_number: '',
  product_id: '',
  batch_number: '',
  manufacture_date: '',
  notes: '',
}

const BLANK_FLAVOR_FORM: AddFlavorForm = {
  name: '',
  sku: '',
  description: '',
  default_price: '',
  sort_order: '',
}

const BLANK_PRODUCT_FORM: AddProductForm = {
  name: '',
  sku: '',
  description: '',
  default_price: '',
}

const MACHINE_STATUSES: StatusFilter[] = [
  'available',
  'reserved',
  'ordered',
  'sold',
  'delivered',
  'returned',
]

// ---------------------------------------------------------------------------
// Stock section helpers (module-level — no re-creation on render)
// ---------------------------------------------------------------------------

type StockAccent = 'accent-blue' | 'accent-cyan' | 'accent-violet'
const STOCK_ACCENT_FALLBACK: StockAccent[] = ['accent-blue', 'accent-cyan', 'accent-violet']

function resolveStockAccent(sku: string | null, index: number): StockAccent {
  if (sku) {
    const s = sku.toUpperCase()
    if (s.startsWith('RO'))   return 'accent-blue'
    if (s.startsWith('AC'))   return 'accent-cyan'
    if (s.startsWith('SUPP')) return 'accent-violet'
  }
  return STOCK_ACCENT_FALLBACK[index % 3] ?? 'accent-blue'
}

function formatStockDate(updatedAt: string): string {
  const date = new Date(updatedAt)
  return `Last updated ${date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type InventoryTab = 'machines' | 'filters' | 'consumables' | 'reservations'

export default function Inventory() {
  const { user, access_token } = useAuth()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<InventoryTab>('machines')

  const [allMachines, setAllMachines]         = useState<Machine[]>([])
  const [consumableStock, setConsumableStock] = useState<ConsumableStock[]>([])
  const [flavors, setFlavors]                 = useState<SupplementFlavor[]>([])
  const [statusFilter, setStatusFilter]       = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter]           = useState<TypeFilter>('all')
  const [machinesLoading, setMachinesLoading] = useState(true)
  const [stockLoading, setStockLoading]       = useState(true)
  const [flavorsLoading, setFlavorsLoading]   = useState(true)
  const [machinesError, setMachinesError]     = useState<string | null>(null)

  // Register form
  const [showRegisterForm, setShowRegisterForm] = useState(false)
  const [formData, setFormData]                 = useState<FormData>(BLANK_FORM)
  const [formErrors, setFormErrors]             = useState<FormErrors>({})
  const [isSubmitting, setIsSubmitting]         = useState(false)
  const [submitError, setSubmitError]           = useState<string | null>(null)
  const [products, setProducts]                 = useState<Product[]>([])
  const [productsLoading, setProductsLoading]   = useState(false)
  const [productsError, setProductsError]       = useState<string | null>(null)

  // Toast
  const [toast, setToast] = useState<Toast | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Stock management modal
  const [modalProduct, setModalProduct] = useState<ConsumableStock | null>(null)
  const [modalFlavor, setModalFlavor]   = useState<SupplementFlavor | null>(null)

  // Delete-confirmation modal state — one of: machine | product | flavor
  type DeleteTarget =
    | { kind: 'machine'; serial: string }
    | { kind: 'product'; sku: string; name: string; batchCount: number }
    | { kind: 'flavor'; id: string; name: string; batchCount: number }
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)

  // Add flavor modal
  const [showAddFlavor, setShowAddFlavor]   = useState(false)
  const [flavorForm, setFlavorForm]         = useState<AddFlavorForm>(BLANK_FLAVOR_FORM)
  const [flavorSaving, setFlavorSaving]     = useState(false)
  const [flavorError, setFlavorError]       = useState<string | null>(null)

  // Add consumable product modal
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [productForm, setProductForm]       = useState<AddProductForm>(BLANK_PRODUCT_FORM)
  const [productSaving, setProductSaving]   = useState(false)
  const [productError, setProductError]     = useState<string | null>(null)

  // Reserve modal (Machines tab → per-row Reserve button)
  const [reserveTarget, setReserveTarget] = useState<Machine | null>(null)

  // Active reservations count (pending + approved) — driven by ReservationsTab
  // and shown on the tab badge.
  const [activeReservationCount, setActiveReservationCount] = useState(0)
  const handleActiveCountChange = useCallback(
    (count: number) => setActiveReservationCount(count),
    [],
  )

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  // Supplement Pack stock entry (used to open modal for flavor cards)
  const supplementStock = useMemo(
    () => consumableStock.find(s => s.product_name.toLowerCase().includes('supplement')) ?? null,
    [consumableStock],
  )

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const fetchMachines = useCallback(
    async (type: TypeFilter) => {
      if (!access_token) return
      setMachinesLoading(true)
      setMachinesError(null)
      try {
        const params = new URLSearchParams()
        if (type !== 'all') params.set('machine_type', type)
        const qs = params.toString() ? `?${params.toString()}` : ''
        const data = await apiGet<Machine[]>(`/api/machines${qs}`, access_token)
        setAllMachines(data)
      } catch (err) {
        setMachinesError(err instanceof Error ? err.message : 'Failed to load machines')
      } finally {
        setMachinesLoading(false)
      }
    },
    [access_token],
  )

  const fetchStock = useCallback(async () => {
    if (!access_token) return
    setStockLoading(true)
    try {
      const data = await apiGet<ConsumableStock[]>('/api/consumable-stock', access_token)
      setConsumableStock(data)
    } catch {
      // Non-critical — section shows empty state
    } finally {
      setStockLoading(false)
    }
  }, [access_token])

  const fetchFlavors = useCallback(async () => {
    if (!access_token) return
    setFlavorsLoading(true)
    try {
      const data = await apiGet<SupplementFlavor[]>('/api/supplement-flavors', access_token)
      setFlavors(data)
    } catch {
      // Non-critical
    } finally {
      setFlavorsLoading(false)
    }
  }, [access_token])

  const fetchProducts = useCallback(async () => {
    if (!access_token) return
    setProductsLoading(true)
    setProductsError(null)
    try {
      const data = await apiGet<Product[]>('/api/products', access_token)
      setProducts(data)
    } catch {
      setProductsError('Failed to load products. Check backend connection.')
    } finally {
      setProductsLoading(false)
    }
  }, [access_token])

  useEffect(() => { fetchMachines(typeFilter) }, [typeFilter, fetchMachines])
  useEffect(() => { fetchStock() }, [fetchStock])
  useEffect(() => { fetchFlavors() }, [fetchFlavors])
  useEffect(() => { fetchProducts() }, [fetchProducts])

  // -------------------------------------------------------------------------
  // Derived state
  // -------------------------------------------------------------------------

  const statusCounts = useMemo<StatusCounts>(() => {
    const counts: StatusCounts = {
      all:       allMachines.length,
      available: 0,
      reserved:  0,
      ordered:   0,
      sold:      0,
      delivered: 0,
      returned:  0,
    }
    for (const m of allMachines) {
      if (MACHINE_STATUSES.includes(m.status as StatusFilter)) {
        ;(counts as Record<string, number>)[m.status]++
      }
    }
    return counts
  }, [allMachines])

  const displayMachines = useMemo(
    () => statusFilter === 'all' ? allMachines : allMachines.filter(m => m.status === statusFilter),
    [allMachines, statusFilter],
  )

  // Split consumable stock by tab
  const filterStocks = useMemo(
    () => consumableStock.filter(s => s.product_name.toLowerCase().includes('filter')),
    [consumableStock],
  )
  const nonFilterStocks = useMemo(
    () => consumableStock.filter(s => !s.product_name.toLowerCase().includes('filter')),
    [consumableStock],
  )

  const rxProducts = useMemo(
    () => products.filter(p => p.is_serialized && p.name.toUpperCase().startsWith('RX')),
    [products],
  )
  const roProducts = useMemo(
    () => products.filter(p => p.is_serialized && p.name.toUpperCase().startsWith('RO')),
    [products],
  )

  // -------------------------------------------------------------------------
  // Toast helpers
  // -------------------------------------------------------------------------

  function showToast(message: string, type: Toast['type']) {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToast({ message, type })
    toastTimerRef.current = setTimeout(() => setToast(null), 4000)
  }

  // -------------------------------------------------------------------------
  // Modal helpers
  // -------------------------------------------------------------------------

  function openProductModal(item: ConsumableStock) {
    setModalProduct(item)
    setModalFlavor(null)
  }

  function openFlavorModal(f: SupplementFlavor) {
    if (!supplementStock) return
    setModalProduct(supplementStock)
    setModalFlavor(f)
  }

  function closeModal() {
    setModalProduct(null)
    setModalFlavor(null)
  }

  // -------------------------------------------------------------------------
  // Add Flavor
  // -------------------------------------------------------------------------

  async function handleAddFlavor(e: { preventDefault(): void }) {
    e.preventDefault()
    if (!flavorForm.name.trim()) { setFlavorError('Name is required'); return }
    if (!flavorForm.sku.trim())  { setFlavorError('SKU is required'); return }

    setFlavorSaving(true)
    setFlavorError(null)
    try {
      const body: Record<string, unknown> = {
        name: flavorForm.name.trim(),
        sku:  flavorForm.sku.trim(),
      }
      if (flavorForm.description.trim()) body.description = flavorForm.description.trim()
      if (flavorForm.default_price) body.default_price = Number(flavorForm.default_price)
      if (flavorForm.sort_order) body.sort_order = Number(flavorForm.sort_order)

      await apiPostAuth('/api/supplement-flavors', body, access_token!)
      setShowAddFlavor(false)
      setFlavorForm(BLANK_FLAVOR_FORM)
      await fetchFlavors()
      showToast('Flavor added successfully', 'success')
    } catch (err) {
      setFlavorError(err instanceof Error ? err.message : 'Failed to add flavor')
    } finally {
      setFlavorSaving(false)
    }
  }

  // -------------------------------------------------------------------------
  // Add Consumable Product
  // -------------------------------------------------------------------------

  async function handleAddProduct(e: { preventDefault(): void }) {
    e.preventDefault()
    if (!productForm.name.trim())         { setProductError('Name is required'); return }
    if (!productForm.sku.trim())          { setProductError('SKU is required'); return }
    if (!productForm.default_price)       { setProductError('Price is required'); return }

    setProductSaving(true)
    setProductError(null)
    try {
      const body: Record<string, unknown> = {
        name:          productForm.name.trim(),
        sku:           productForm.sku.trim(),
        category:      'consumable',
        default_price: Number(productForm.default_price),
        is_serialized: false,
      }
      if (productForm.description.trim()) body.description = productForm.description.trim()

      await apiPostAuth('/api/products', body, access_token!)
      setShowAddProduct(false)
      setProductForm(BLANK_PRODUCT_FORM)
      await Promise.all([fetchStock(), fetchProducts()])
      showToast('Product added successfully', 'success')
    } catch (err) {
      setProductError(err instanceof Error ? err.message : 'Failed to add product')
    } finally {
      setProductSaving(false)
    }
  }

  // -------------------------------------------------------------------------
  // Delete / deactivate handlers
  // -------------------------------------------------------------------------

  async function handleDeleteMachine(serial: string) {
    await apiDelete(`/api/machines/${encodeURIComponent(serial)}`, access_token!)
    setAllMachines(prev => prev.filter(m => m.serial_number !== serial))
    showToast(`Machine ${serial} removed`, 'success')
  }

  async function handleDeactivateProduct(sku: string, name: string) {
    await apiPut(`/api/products/${encodeURIComponent(sku)}`, { is_active: false }, access_token!)
    setConsumableStock(prev => prev.filter(s => s.product_sku !== sku))
    showToast(`${name} deactivated`, 'success')
  }

  async function handleDeactivateFlavor(id: string, name: string) {
    await apiDelete(`/api/supplement-flavors/${id}`, access_token!)
    setFlavors(prev => prev.filter(f => f.id !== id))
    showToast(`Flavor "${name}" deactivated`, 'success')
  }

  // Wraps the per-target delete handlers for the ConfirmModal callback.
  async function performDelete() {
    if (!deleteTarget) return
    if (deleteTarget.kind === 'machine') {
      await handleDeleteMachine(deleteTarget.serial)
    } else if (deleteTarget.kind === 'product') {
      await handleDeactivateProduct(deleteTarget.sku, deleteTarget.name)
    } else if (deleteTarget.kind === 'flavor') {
      await handleDeactivateFlavor(deleteTarget.id, deleteTarget.name)
    }
    setDeleteTarget(null)
  }

  // -------------------------------------------------------------------------
  // Machine form handlers
  // -------------------------------------------------------------------------

  function handleTypeChange(type: TypeFilter) {
    setTypeFilter(type)
    setStatusFilter('all')
  }

  function openRegisterForm() {
    setShowRegisterForm(true)
    setFormData(BLANK_FORM)
    setFormErrors({})
    setSubmitError(null)
  }

  function closeRegisterForm() {
    setShowRegisterForm(false)
    setFormData(BLANK_FORM)
    setFormErrors({})
    setSubmitError(null)
  }

  function handleFieldChange<K extends keyof FormData>(field: K, value: FormData[K]) {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (formErrors[field as keyof FormErrors]) {
      setFormErrors(prev => ({ ...prev, [field]: undefined }))
    }
  }

  function validate(): FormErrors {
    const errors: FormErrors = {}
    if (!formData.serial_number.trim()) errors.serial_number = 'Serial number is required'
    if (!formData.product_id)           errors.product_id    = 'Product is required'
    if (!formData.batch_number.trim())  errors.batch_number  = 'Batch number is required'
    if (!formData.manufacture_date) {
      errors.manufacture_date = 'Manufacture date is required'
    } else {
      const year = new Date(formData.manufacture_date).getFullYear()
      if (isNaN(year) || year > 2099) errors.manufacture_date = 'Please enter a valid date'
    }
    return errors
  }

  async function handleSubmit(e: { preventDefault(): void }) {
    e.preventDefault()
    const errors = validate()
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors)
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)

    try {
      const selectedProduct = products.find(p => p.id === formData.product_id)
      const derivedMachineType = selectedProduct?.name.toUpperCase().startsWith('RX') ? 'RX'
        : selectedProduct?.name.toUpperCase().startsWith('RO') ? 'RO'
        : null
      const body: Record<string, string> = {
        serial_number:    formData.serial_number.trim(),
        product_id:       formData.product_id,
        batch_number:     formData.batch_number.trim(),
        manufacture_date: formData.manufacture_date,
      }
      if (derivedMachineType) body.machine_type = derivedMachineType
      if (formData.notes.trim()) body.notes = formData.notes.trim()

      await apiPostAuth('/api/machines', body, access_token!)

      showToast(`Machine ${formData.serial_number.trim()} registered successfully`, 'success')
      setFormData(BLANK_FORM)
      setFormErrors({})
      fetchMachines(typeFilter)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="inventory-page">
      <h1 className="inv-heading">Inventory</h1>

      <div className="inv-tabs">
        <button
          className={`inv-tab${activeTab === 'machines' ? ' inv-tab-active' : ''}`}
          onClick={() => setActiveTab('machines')}
        >
          <Package size={14} /> Machines
        </button>
        <button
          className={`inv-tab${activeTab === 'filters' ? ' inv-tab-active' : ''}`}
          onClick={() => setActiveTab('filters')}
        >
          <FilterIcon size={14} /> Filters
        </button>
        <button
          className={`inv-tab${activeTab === 'consumables' ? ' inv-tab-active' : ''}`}
          onClick={() => setActiveTab('consumables')}
        >
          <Beaker size={14} /> Consumables
        </button>
        <button
          className={`inv-tab${activeTab === 'reservations' ? ' inv-tab-active' : ''}`}
          onClick={() => setActiveTab('reservations')}
        >
          <CalendarCheck size={14} /> Reservations
          {activeReservationCount > 0 && (
            <span className="inv-tab-badge">{activeReservationCount}</span>
          )}
        </button>
      </div>

      {activeTab === 'machines' && (
      <>
      <FilterBar
        statusFilter={statusFilter}
        typeFilter={typeFilter}
        statusCounts={statusCounts}
        isAdmin={isAdmin}
        onStatusChange={setStatusFilter}
        onTypeChange={handleTypeChange}
        onRegisterClick={openRegisterForm}
      />

      {/* Register Machine Form */}
      {showRegisterForm && (
        <div className="register-form-container">
          <div className="register-form-header">
            <span className="register-form-title">Register New Machine</span>
            <button
              className="register-form-close"
              onClick={closeRegisterForm}
              aria-label="Close form"
            >
              <X size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} noValidate>
            <div className="register-form-grid">

              <div className="register-field">
                <label className="register-label">Serial Number</label>
                <input
                  className={`register-input register-input-mono${formErrors.serial_number ? ' input-error' : ''}`}
                  type="text"
                  placeholder="e.g. RX-2026-001"
                  value={formData.serial_number}
                  onChange={e => handleFieldChange('serial_number', e.target.value)}
                  disabled={isSubmitting}
                />
                {formErrors.serial_number && (
                  <span className="register-field-error">{formErrors.serial_number}</span>
                )}
              </div>

              <div className="register-field">
                <label className="register-label">Batch Number</label>
                <input
                  className={`register-input${formErrors.batch_number ? ' input-error' : ''}`}
                  type="text"
                  placeholder="e.g. B2026-01"
                  value={formData.batch_number}
                  onChange={e => handleFieldChange('batch_number', e.target.value)}
                  disabled={isSubmitting}
                />
                {formErrors.batch_number && (
                  <span className="register-field-error">{formErrors.batch_number}</span>
                )}
              </div>

              <div className="register-field register-field-full">
                <label className="register-label">Product</label>
                {productsError ? (
                  <span className="register-field-error">{productsError}</span>
                ) : (
                  <select
                    className={`register-input${formErrors.product_id ? ' input-error' : ''}`}
                    value={formData.product_id}
                    onChange={e => handleFieldChange('product_id', e.target.value)}
                    disabled={isSubmitting || productsLoading}
                  >
                    <option value="">
                      {productsLoading ? 'Loading products…' : 'Select a product…'}
                    </option>
                    {!productsLoading && rxProducts.length > 0 && (
                      <optgroup label="RX Machines">
                        {rxProducts.map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </optgroup>
                    )}
                    {!productsLoading && roProducts.length > 0 && (
                      <optgroup label="RO Machines">
                        {roProducts.map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </optgroup>
                    )}
                    {!productsLoading && rxProducts.length === 0 && roProducts.length === 0 && (
                      <option value="" disabled>No machine products available</option>
                    )}
                  </select>
                )}
                {formErrors.product_id && (
                  <span className="register-field-error">{formErrors.product_id}</span>
                )}
              </div>

              <div className="register-field">
                <label className="register-label">Manufacture Date</label>
                <input
                  className={`register-input${formErrors.manufacture_date ? ' input-error' : ''}`}
                  type="date"
                  value={formData.manufacture_date}
                  onChange={e => handleFieldChange('manufacture_date', e.target.value)}
                  disabled={isSubmitting}
                />
                {formErrors.manufacture_date && (
                  <span className="register-field-error">{formErrors.manufacture_date}</span>
                )}
              </div>

              <div className="register-field register-field-full">
                <label className="register-label">
                  Notes <span className="register-label-optional">(optional)</span>
                </label>
                <textarea
                  className="register-input register-textarea"
                  rows={2}
                  placeholder="Any notes about this machine…"
                  value={formData.notes}
                  onChange={e => handleFieldChange('notes', e.target.value)}
                  disabled={isSubmitting}
                />
              </div>

            </div>

            {submitError && (
              <p className="register-submit-error">{submitError}</p>
            )}

            <div className="register-form-actions">
              <button
                type="button"
                className="register-btn-cancel"
                onClick={closeRegisterForm}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="register-btn-submit"
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 size={14} className="register-spinner" />
                    Registering…
                  </>
                ) : (
                  'Register Machine'
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {machinesError ? (
        <div className="inventory-error">
          <p className="inventory-error-text">{machinesError}</p>
          <button className="inventory-error-retry" onClick={() => fetchMachines(typeFilter)}>
            Retry
          </button>
        </div>
      ) : (
        <p className="inventory-count">
          Showing {displayMachines.length} of {allMachines.length} machine
          {allMachines.length !== 1 ? 's' : ''}
        </p>
      )}

      <MachineTable
        machines={displayMachines}
        loading={machinesLoading}
        onRowClick={(m) => navigate(`/machines/${m.serial_number}`)}
        onDelete={isAdmin ? (m) => setDeleteTarget({ kind: 'machine', serial: m.serial_number }) : undefined}
        onReserve={(m) => setReserveTarget(m)}
      />
      </>
      )}

      {activeTab === 'reservations' && user && (
        <ReservationsTab
          currentUserId={user.id}
          isAdmin={isAdmin}
          token={access_token!}
          showToast={showToast}
          onActiveCountChange={handleActiveCountChange}
        />
      )}

      {/* ── Consumable Stock Section (Filters / Consumables tabs) ── */}
      {(activeTab === 'filters' || activeTab === 'consumables') && (
      <section className="stock-section">
        <div className="stock-section-header">
          <h2 className="stock-section-title">
            {activeTab === 'filters' ? 'Filter Products' : 'Consumables'}
          </h2>
          {isAdmin && (
            <button
              className="stock-add-product-btn"
              onClick={() => { setShowAddProduct(true); setProductForm(BLANK_PRODUCT_FORM); setProductError(null) }}
            >
              <Plus size={12} />
              Add New Consumable Product
            </button>
          )}
        </div>

        {/* Add Consumable Product inline form */}
        {showAddProduct && isAdmin && (
          <form className="stock-add-form" onSubmit={handleAddProduct} noValidate>
            <p className="stock-add-form-title">New Consumable Product</p>
            <div className="stock-add-form-grid">
              <div className="stock-add-field">
                <label className="stock-add-label">Name</label>
                <input
                  className="register-input"
                  placeholder="e.g. AC Filter"
                  value={productForm.name}
                  onChange={e => setProductForm(f => ({ ...f, name: e.target.value }))}
                  disabled={productSaving}
                />
              </div>
              <div className="stock-add-field">
                <label className="stock-add-label">SKU</label>
                <input
                  className="register-input register-input-mono"
                  placeholder="e.g. AC-FILTER-01"
                  value={productForm.sku}
                  onChange={e => setProductForm(f => ({ ...f, sku: e.target.value }))}
                  disabled={productSaving}
                />
              </div>
              <div className="stock-add-field">
                <label className="stock-add-label">Default Price ($)</label>
                <input
                  type="number"
                  className="register-input"
                  placeholder="0.00"
                  min={0}
                  step="0.01"
                  value={productForm.default_price}
                  onChange={e => setProductForm(f => ({ ...f, default_price: e.target.value }))}
                  disabled={productSaving}
                />
              </div>
              <div className="stock-add-field">
                <label className="stock-add-label">Description <span className="register-label-optional">(opt)</span></label>
                <input
                  className="register-input"
                  placeholder="Brief description…"
                  value={productForm.description}
                  onChange={e => setProductForm(f => ({ ...f, description: e.target.value }))}
                  disabled={productSaving}
                />
              </div>
            </div>
            {productError && <p className="register-submit-error">{productError}</p>}
            <div className="register-form-actions">
              <button
                type="button"
                className="register-btn-cancel"
                onClick={() => { setShowAddProduct(false); setProductError(null) }}
                disabled={productSaving}
              >
                Cancel
              </button>
              <button type="submit" className="register-btn-submit" disabled={productSaving}>
                {productSaving ? <><Loader2 size={14} className="register-spinner" />Adding…</> : 'Add Product'}
              </button>
            </div>
          </form>
        )}

        {/* Stock cards */}
        <div className="stock-cards">
          {stockLoading ? (
            <>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="stock-card-skeleton">
                  <div className="skeleton-line h-sm w-short" />
                  <div className="skeleton-line h-lg w-mid" />
                  <div className="skeleton-line h-sm w-long" />
                </div>
              ))}
            </>
          ) : (activeTab === 'filters' ? filterStocks : nonFilterStocks).length === 0 ? (
            <p className="stock-empty">
              {activeTab === 'filters' ? 'No filter products available.' : 'No consumable stock data available.'}
            </p>
          ) : (
            (activeTab === 'filters' ? filterStocks : nonFilterStocks).map((item, i) => {
              const isSupp = item.product_name.toLowerCase().includes('supplement')
              const threshold = item.min_threshold ?? 10
              const isLow = item.quantity < threshold
              return (
                <div
                  key={item.product_id}
                  className={`stock-card ${resolveStockAccent(item.product_sku, i)} stock-card-clickable`}
                  onClick={() => openProductModal(item)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter') openProductModal(item) }}
                >
                  {isAdmin && (
                    <div className="stock-card-icon-row">
                      {activeTab === 'filters' && (
                        <button
                          className="stock-card-icon-btn"
                          title="Edit / manage batches"
                          onClick={e => { e.stopPropagation(); openProductModal(item) }}
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      <button
                        className="stock-card-icon-btn stock-card-icon-btn-danger"
                        title="Deactivate product"
                        onClick={e => {
                          e.stopPropagation()
                          if (!item.product_sku) return
                          setDeleteTarget({
                            kind: 'product',
                            sku: item.product_sku,
                            name: item.product_name,
                            batchCount: item.batch_count,
                          })
                        }}
                      >
                        <X size={12} />
                      </button>
                    </div>
                  )}
                  <p className="stock-card-name">{item.product_name}</p>
                  {item.product_sku && (
                    <p className="stock-card-sku">{item.product_sku}</p>
                  )}
                  <div className="flex items-baseline gap-2 mb-1">
                    <p className="stock-card-qty mb-0">{item.quantity}</p>
                    {isLow && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-400/10 text-amber-400">
                        Low Stock
                      </span>
                    )}
                  </div>
                  <p className="stock-card-meta">
                    in stock · ${item.default_price.toFixed(2)}
                    {isSupp && item.batch_count > 0 && ` · ${item.batch_count} batch${item.batch_count !== 1 ? 'es' : ''}`}
                  </p>
                  <p className="text-[11px] text-[#64748B] mt-1">
                    {formatStockDate(item.updated_at)}
                  </p>
                  {isAdmin && (
                    <button
                      className="stock-card-update-btn"
                      onClick={e => { e.stopPropagation(); openProductModal(item) }}
                    >
                      Manage Batches
                    </button>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Flavor cards (below Supplement Pack) — Consumables tab only */}
        {activeTab === 'consumables' && !flavorsLoading && flavors.length > 0 && (
          <div className="flavor-cards-row">
            {flavors.map(f => (
              <div
                key={f.id}
                className="flavor-card"
                onClick={() => openFlavorModal(f)}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter') openFlavorModal(f) }}
              >
                {isAdmin && (
                  <button
                    className="flavor-card-delete-btn"
                    title="Deactivate flavor"
                    onClick={e => {
                      e.stopPropagation()
                      setDeleteTarget({
                        kind: 'flavor',
                        id: f.id,
                        name: f.name,
                        batchCount: f.batch_count,
                      })
                    }}
                  >
                    <Trash2 size={12} />
                  </button>
                )}
                <p className="flavor-card-name">{f.name}</p>
                {f.sku && <p className="flavor-card-sku">{f.sku}</p>}
                <p className="flavor-card-qty">{f.total_in_stock}</p>
                <p className="flavor-card-meta">
                  {f.batch_count} batch{f.batch_count !== 1 ? 'es' : ''}
                  {f.default_price != null && ` · $${f.default_price.toFixed(2)}`}
                </p>
              </div>
            ))}

            {/* Add Flavor card (admin only) */}
            {isAdmin && (
              <div
                className="flavor-card flavor-card-add"
                onClick={() => { setShowAddFlavor(true); setFlavorForm(BLANK_FLAVOR_FORM); setFlavorError(null) }}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter') setShowAddFlavor(true) }}
              >
                <span className="flavor-card-add-icon">+</span>
                <span className="flavor-card-add-label">Add Flavor</span>
              </div>
            )}
          </div>
        )}

        {/* Add Flavor modal — Consumables tab only */}
        {activeTab === 'consumables' && showAddFlavor && isAdmin && (
          <div className="sm-overlay" onClick={e => { if (e.target === e.currentTarget) setShowAddFlavor(false) }}>
            <div className="sm-container" style={{ maxWidth: 480 }}>
              <div className="sm-header">
                <div className="sm-header-title-row">
                  <h2 className="sm-title">Add Supplement Flavor</h2>
                  <button className="sm-close-btn" onClick={() => setShowAddFlavor(false)}><X size={18} /></button>
                </div>
              </div>
              <form onSubmit={handleAddFlavor} noValidate>
                <div className="stock-add-form-grid" style={{ padding: '20px 24px' }}>
                  <div className="stock-add-field">
                    <label className="stock-add-label">Name</label>
                    <input
                      className="sm-inline-input"
                      placeholder="e.g. Berry Blast"
                      value={flavorForm.name}
                      onChange={e => setFlavorForm(f => ({ ...f, name: e.target.value }))}
                      disabled={flavorSaving}
                    />
                  </div>
                  <div className="stock-add-field">
                    <label className="stock-add-label">SKU</label>
                    <input
                      className="sm-inline-input sm-mono"
                      placeholder="e.g. SUPP-BERRY-01"
                      value={flavorForm.sku}
                      onChange={e => setFlavorForm(f => ({ ...f, sku: e.target.value }))}
                      disabled={flavorSaving}
                    />
                  </div>
                  <div className="stock-add-field">
                    <label className="stock-add-label">Price ($) <span className="register-label-optional">(opt)</span></label>
                    <input
                      type="number"
                      className="sm-inline-input"
                      placeholder="0.00"
                      min={0}
                      step="0.01"
                      value={flavorForm.default_price}
                      onChange={e => setFlavorForm(f => ({ ...f, default_price: e.target.value }))}
                      disabled={flavorSaving}
                    />
                  </div>
                  <div className="stock-add-field">
                    <label className="stock-add-label">Sort Order <span className="register-label-optional">(opt)</span></label>
                    <input
                      type="number"
                      className="sm-inline-input"
                      placeholder="0"
                      min={0}
                      value={flavorForm.sort_order}
                      onChange={e => setFlavorForm(f => ({ ...f, sort_order: e.target.value }))}
                      disabled={flavorSaving}
                    />
                  </div>
                  <div className="stock-add-field stock-add-field-full">
                    <label className="stock-add-label">Description <span className="register-label-optional">(opt)</span></label>
                    <input
                      className="sm-inline-input"
                      placeholder="Brief description…"
                      value={flavorForm.description}
                      onChange={e => setFlavorForm(f => ({ ...f, description: e.target.value }))}
                      disabled={flavorSaving}
                    />
                  </div>
                </div>
                {flavorError && <p className="register-submit-error" style={{ margin: '0 24px' }}>{flavorError}</p>}
                <div className="sm-footer">
                  <button
                    type="button"
                    className="sm-btn-close-footer"
                    onClick={() => setShowAddFlavor(false)}
                    disabled={flavorSaving}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="sm-btn-add" disabled={flavorSaving} style={{ marginLeft: 8 }}>
                    {flavorSaving ? 'Adding…' : 'Add Flavor'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </section>
      )}

      {/* Stock Management Modal */}
      {modalProduct && (
        <StockModal
          product={modalProduct}
          flavor={modalFlavor}
          flavors={flavors}
          accessToken={access_token ?? ''}
          isAdmin={isAdmin}
          onClose={closeModal}
          onStockUpdated={() => { fetchStock(); fetchFlavors() }}
        />
      )}

      {/* Delete / deactivate confirm modal */}
      {deleteTarget && deleteTarget.kind === 'machine' && (
        <ConfirmModal
          title="Remove Machine"
          message={
            <>
              Are you sure you want to remove machine{' '}
              <strong>{deleteTarget.serial}</strong>? This action cannot be undone.
            </>
          }
          warning="If this machine has an active warranty, reservation, or open issues, the server will block the delete and prompt you to remove them first."
          confirmLabel="Remove"
          confirmKind="danger"
          onConfirm={performDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {deleteTarget && deleteTarget.kind === 'product' && (
        <ConfirmModal
          title="Remove Product"
          message={
            <>
              Are you sure you want to deactivate{' '}
              <strong>{deleteTarget.name}</strong>? It will be hidden from the
              catalog.
            </>
          }
          warning={
            deleteTarget.batchCount > 0
              ? `This product has ${deleteTarget.batchCount} batch${deleteTarget.batchCount === 1 ? '' : 'es'}. They will also be hidden.`
              : null
          }
          confirmLabel="Deactivate"
          confirmKind="danger"
          onConfirm={performDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {deleteTarget && deleteTarget.kind === 'flavor' && (
        <ConfirmModal
          title="Remove Flavor"
          message={
            <>
              Deactivate flavor <strong>{deleteTarget.name}</strong>? It will be
              hidden from the catalog.
            </>
          }
          warning={
            deleteTarget.batchCount > 0
              ? `This flavor has ${deleteTarget.batchCount} batch${deleteTarget.batchCount === 1 ? '' : 'es'}. They will also be hidden.`
              : null
          }
          confirmLabel="Deactivate"
          confirmKind="danger"
          onConfirm={performDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Reserve Machine modal — opened from MachineTable rows */}
      {reserveTarget && access_token && (
        <ReserveMachineModal
          identifier={reserveTarget.serial_number}
          serial={reserveTarget.serial_number}
          machineType={reserveTarget.machine_type}
          currentStatus={reserveTarget.status}
          token={access_token}
          onClose={() => setReserveTarget(null)}
          onCreated={() => {
            setReserveTarget(null)
            showToast('Reservation submitted! Awaiting admin approval.', 'success')
            // Refresh machine list so any backend-side state shifts are visible.
            fetchMachines(typeFilter)
          }}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className={`inventory-toast inventory-toast-${toast.type}`}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
