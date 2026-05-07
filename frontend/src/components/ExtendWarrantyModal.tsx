import { useState, useMemo } from 'react'
import { Plus } from 'lucide-react'
import { apiPut } from '../lib/api'
import { useAuth } from '../lib/auth'
import './ExtendWarrantyModal.css'

interface Props {
  isOpen: boolean
  onClose: () => void
  warrantyId: string
  serialNumber: string
  /** ISO date string (yyyy-mm-dd) for the warranty's current end_date. */
  currentEndDate: string
  /** Current duration in months — shown in the "Current info" section. */
  currentDuration: number
  /** Optional days_remaining for color cue; recomputed if absent. */
  daysRemaining?: number | null
  /** Called after a successful extension. Parent should refresh data. */
  onSuccess: () => void
}

// ─── Date helpers ─────────────────────────────────────────────────────────

function formatDate(value: string): string {
  try {
    return new Date(value + 'T00:00:00').toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  } catch {
    return value
  }
}

/** Add `months` to a date, clamping the day to the last day of the target month. */
function addMonths(date: Date, months: number): Date {
  const result = new Date(date.getFullYear(), date.getMonth() + months, 1)
  const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate()
  result.setDate(Math.min(date.getDate(), lastDay))
  return result
}

function formatDateOnly(d: Date): string {
  return d.toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

/** Days from today (UTC midnight) to the given ISO date. */
function computeDaysRemaining(endDate: string): number {
  const end = new Date(endDate + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.floor((end.getTime() - today.getTime()) / 86400000)
}

// ─── Component ────────────────────────────────────────────────────────────

export default function ExtendWarrantyModal({
  isOpen,
  onClose,
  warrantyId,
  serialNumber,
  currentEndDate,
  currentDuration,
  daysRemaining,
  onSuccess,
}: Props) {
  const { access_token } = useAuth()
  const [months, setMonths] = useState(6)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const computedDaysRemaining = useMemo(
    () => daysRemaining ?? computeDaysRemaining(currentEndDate),
    [currentEndDate, daysRemaining],
  )

  const newEndDate = useMemo(() => {
    try {
      return formatDateOnly(
        addMonths(new Date(currentEndDate + 'T00:00:00'), months || 0),
      )
    } catch {
      return '—'
    }
  }, [currentEndDate, months])

  if (!isOpen) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reason.trim()) {
      setErr('Reason is required')
      return
    }
    if (months < 1) {
      setErr('Additional months must be at least 1')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      await apiPut(
        `/api/warranty/${warrantyId}/extend`,
        { additional_months: months, reason: reason.trim() },
        access_token!,
      )
      onSuccess()
      onClose()
      // Reset form for next open
      setMonths(6)
      setReason('')
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const daysClass =
    computedDaysRemaining < 0 ? 'ext-days-expired'
    : computedDaysRemaining < 7 ? 'ext-days-critical'
    : computedDaysRemaining <= 30 ? 'ext-days-warn'
    : 'ext-days-ok'

  return (
    <div className="ext-modal-overlay" onClick={onClose}>
      <form
        className="ext-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="ext-modal-title">Extend Warranty — {serialNumber}</h3>

        {/* Current info pane */}
        <div className="ext-current-info">
          <div className="ext-info-row">
            <span className="ext-info-label">Current end date</span>
            <strong>{formatDate(currentEndDate)}</strong>
          </div>
          <div className="ext-info-row">
            <span className="ext-info-label">Current duration</span>
            <strong>{currentDuration} months</strong>
          </div>
          <div className="ext-info-row">
            <span className="ext-info-label">Days remaining</span>
            <strong className={daysClass}>
              {computedDaysRemaining < 0
                ? `${Math.abs(computedDaysRemaining)}d expired`
                : `${computedDaysRemaining}d`}
            </strong>
          </div>
        </div>

        <label className="ext-field">
          <span>Additional Months</span>
          <input
            type="number"
            min={1}
            max={60}
            value={months}
            onChange={(e) => setMonths(parseInt(e.target.value || '6', 10))}
            disabled={saving}
          />
        </label>

        <label className="ext-field">
          <span>Reason *</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Reason for extension..."
            disabled={saving}
          />
        </label>

        <p className="ext-new-end-line">
          New end date: <strong>{newEndDate}</strong>
        </p>

        {err && <div className="ext-form-error">{err}</div>}

        <div className="ext-modal-actions">
          <button
            type="button"
            className="ext-btn ext-btn-ghost"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ext-btn ext-btn-primary"
            disabled={saving}
          >
            <Plus size={14} />
            {saving ? 'Extending…' : 'Extend Warranty'}
          </button>
        </div>
      </form>
    </div>
  )
}
