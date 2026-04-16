import './FilterBar.css'
import type { StatusFilter, TypeFilter, StatusCounts } from './types'

interface Props {
  statusFilter: StatusFilter
  typeFilter: TypeFilter
  statusCounts: StatusCounts
  isAdmin: boolean
  onStatusChange: (s: StatusFilter) => void
  onTypeChange: (t: TypeFilter) => void
  onRegisterClick?: () => void
}

const STATUS_TABS: { value: StatusFilter; label: string }[] = [
  { value: 'all',       label: 'All'       },
  { value: 'available', label: 'Available' },
  { value: 'reserved',  label: 'Reserved'  },
  { value: 'ordered',   label: 'Ordered'   },
  { value: 'sold',      label: 'Sold'      },
  { value: 'delivered', label: 'Delivered' },
  { value: 'returned',  label: 'Returned'  },
]

const TYPE_TABS: { value: TypeFilter; label: string }[] = [
  { value: 'all', label: 'All Types'  },
  { value: 'RX',  label: 'RX Machine' },
  { value: 'RO',  label: 'RO Machine' },
]

export default function FilterBar({
  statusFilter,
  typeFilter,
  statusCounts,
  isAdmin,
  onStatusChange,
  onTypeChange,
  onRegisterClick,
}: Props) {
  return (
    <div className="filter-bar">

      {/* Status tabs */}
      <div className="filter-status-tabs">
        {STATUS_TABS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => onStatusChange(value)}
            className={`filter-tab${statusFilter === value ? ' active-status' : ''}`}
          >
            {label} ({statusCounts[value]})
          </button>
        ))}
      </div>

      <div className="filter-divider" />

      {/* Type tabs */}
      <div className="filter-type-tabs">
        {TYPE_TABS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => onTypeChange(value)}
            className={`filter-tab${typeFilter === value ? ' active-type' : ''}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Register Machine — admin only */}
      {isAdmin && (
        <button className="filter-register-btn" onClick={onRegisterClick}>
          + Register Machine
        </button>
      )}
    </div>
  )
}
