import { Trash2 } from 'lucide-react'
import './MachineTable.css'
import type { Machine } from './types'

interface Props {
  machines: Machine[]
  loading: boolean
  onRowClick?: (machine: Machine) => void
  onDelete?: (machine: Machine) => void
}

const COLUMNS = ['Serial Number', 'Type', 'Batch', 'Mfg Date', 'Status', 'Linked To'] as const

// One width modifier per column for the loading skeleton
const SKELETON_WIDTHS = ['w-lg', 'w-xs', 'w-sm', 'w-md', 'w-sm', 'w-xs'] as const

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

function SkeletonRows({ extraCol }: { extraCol?: boolean }) {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <tr key={i} className="machine-row">
          {SKELETON_WIDTHS.map((w, j) => (
            <td key={j}>
              <div className={`skeleton-cell ${w}`} />
            </td>
          ))}
          {extraCol && (
            <td>
              <div className="skeleton-cell w-xs" />
            </td>
          )}
        </tr>
      ))}
    </>
  )
}

export default function MachineTable({ machines, loading, onRowClick, onDelete }: Props) {
  return (
    <div className="machine-table-wrap">
      <table className="machine-table">
        <thead>
          <tr>
            {COLUMNS.map(col => (
              <th key={col}>{col}</th>
            ))}
            {onDelete && <th className="machine-actions-col"></th>}
          </tr>
        </thead>

        <tbody>
          {loading ? (
            <SkeletonRows extraCol={!!onDelete} />
          ) : machines.length === 0 ? (
            <tr>
              <td colSpan={onDelete ? 7 : 6} className="machine-empty">
                No machines registered yet
              </td>
            </tr>
          ) : (
            machines.map(machine => {
              const type = machine.machine_type

              return (
                <tr
                  key={machine.id}
                  className={`machine-row${onRowClick ? ' machine-row-clickable' : ''}`}
                  onClick={onRowClick ? () => onRowClick(machine) : undefined}
                >
                  {/* Serial Number */}
                  <td>
                    <span className="machine-serial">{machine.serial_number}</span>
                  </td>

                  {/* Type badge */}
                  <td>
                    {type === 'RX' || type === 'RO' ? (
                      <span className={`machine-type-badge ${type.toLowerCase()}`}>
                        {type}
                      </span>
                    ) : (
                      <span className="machine-muted">—</span>
                    )}
                  </td>

                  {/* Batch */}
                  <td>
                    <span className="machine-muted">{machine.batch_number}</span>
                  </td>

                  {/* Mfg Date */}
                  <td>
                    <span className="machine-muted">{formatDate(machine.manufacture_date)}</span>
                  </td>

                  {/* Status badge */}
                  <td>
                    <span className={`status-badge status-${machine.status}`}>
                      <span className="status-dot" />
                      {machine.status.charAt(0).toUpperCase() + machine.status.slice(1)}
                    </span>
                  </td>

                  {/* Linked To */}
                  <td>
                    <span className="machine-muted">—</span>
                  </td>

                  {/* Delete action (admin only — when prop provided) */}
                  {onDelete && (
                    <td className="machine-actions-col">
                      <button
                        className="machine-delete-btn"
                        title="Remove machine"
                        onClick={(e) => {
                          e.stopPropagation()
                          onDelete(machine)
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
