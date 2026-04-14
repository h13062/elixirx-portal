import { useState, useEffect, useCallback, useMemo } from 'react'
import './Inventory.css'
import { useAuth } from '../lib/auth'
import { apiGet } from '../lib/api'
import FilterBar from '../components/inventory/FilterBar'
import MachineTable from '../components/inventory/MachineTable'
import ConsumableStockSection from '../components/inventory/ConsumableStockSection'
import type {
  Machine,
  ConsumableStock,
  StatusFilter,
  TypeFilter,
  StatusCounts,
} from '../components/inventory/types'

const MACHINE_STATUSES: StatusFilter[] = [
  'available',
  'reserved',
  'ordered',
  'sold',
  'delivered',
  'returned',
]

export default function Inventory() {
  const { user, access_token } = useAuth()

  const [allMachines, setAllMachines]         = useState<Machine[]>([])
  const [consumableStock, setConsumableStock] = useState<ConsumableStock[]>([])
  const [statusFilter, setStatusFilter]       = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter]           = useState<TypeFilter>('all')
  const [machinesLoading, setMachinesLoading] = useState(true)
  const [stockLoading, setStockLoading]       = useState(true)
  const [machinesError, setMachinesError]     = useState<string | null>(null)

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

  useEffect(() => {
    fetchMachines(typeFilter)
  }, [typeFilter, fetchMachines])

  useEffect(() => {
    fetchStock()
  }, [fetchStock])

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

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  function handleTypeChange(type: TypeFilter) {
    setTypeFilter(type)
    setStatusFilter('all')
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
      />

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
    </div>
  )
}
