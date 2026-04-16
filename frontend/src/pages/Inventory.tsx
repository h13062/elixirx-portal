import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import './Inventory.css'
import { useAuth } from '../lib/auth'
import { apiGet } from '../lib/api'
import FilterBar from '../components/inventory/FilterBar'
import MachineTable from '../components/inventory/MachineTable'
import ConsumableStockSection from '../components/inventory/ConsumableStockSection'
import type {
  Machine,
  ConsumableStock,
  Product,
  StatusFilter,
  TypeFilter,
  StatusCounts,
} from '../components/inventory/types'
import { X, Loader2 } from 'lucide-react'

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

const BLANK_FORM: FormData = {
  serial_number: '',
  product_id: '',
  batch_number: '',
  manufacture_date: '',
  notes: '',
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
// Component
// ---------------------------------------------------------------------------

export default function Inventory() {
  const { user, access_token } = useAuth()

  const [allMachines, setAllMachines]         = useState<Machine[]>([])
  const [consumableStock, setConsumableStock] = useState<ConsumableStock[]>([])
  const [statusFilter, setStatusFilter]       = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter]           = useState<TypeFilter>('all')
  const [machinesLoading, setMachinesLoading] = useState(true)
  const [stockLoading, setStockLoading]       = useState(true)
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

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

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

  useEffect(() => {
    fetchMachines(typeFilter)
  }, [typeFilter, fetchMachines])

  useEffect(() => {
    fetchStock()
  }, [fetchStock])

  // Fetch products on mount so the grouped dropdown is ready when the form opens
  useEffect(() => {
    fetchProducts()
  }, [fetchProducts])

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
    () =>
      statusFilter === 'all'
        ? allMachines
        : allMachines.filter(m => m.status === statusFilter),
    [allMachines, statusFilter],
  )

  // Serialized products only — grouped by name prefix (matches backend _derive_machine_type).
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
  // Form handlers
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
      const BASE_URL = import.meta.env.VITE_API_URL as string
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

      const res = await fetch(`${BASE_URL}/api/machines`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${access_token}`,
        },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data?.detail || data?.message || `Error ${res.status}`)
      }

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

              {/* Row 1: Serial Number | Batch Number */}
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

              {/* Row 2: Product — full width, grouped by machine type */}
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

              {/* Row 3: Manufacture Date */}
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

              {/* Row 4: Notes — full width */}
              <div className="register-field register-field-full">
                <label className="register-label">Notes <span className="register-label-optional">(optional)</span></label>
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

            {/* Submit error */}
            {submitError && (
              <p className="register-submit-error">{submitError}</p>
            )}

            {/* Actions */}
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
          <button
            className="inventory-error-retry"
            onClick={() => fetchMachines(typeFilter)}
          >
            Retry
          </button>
        </div>
      ) : (
        <p className="inventory-count">
          Showing {displayMachines.length} of {allMachines.length} machine
          {allMachines.length !== 1 ? 's' : ''}
        </p>
      )}

      <MachineTable machines={displayMachines} loading={machinesLoading} />

      <ConsumableStockSection stock={consumableStock} loading={stockLoading} />

      {/* Toast */}
      {toast && (
        <div className={`inventory-toast inventory-toast-${toast.type}`}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
