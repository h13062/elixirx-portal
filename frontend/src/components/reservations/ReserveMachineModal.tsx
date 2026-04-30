import { useState } from 'react'
import { apiPostAuth } from '../../lib/api'
import './Reservations.css'

interface Props {
  /** UUID or serial — backend resolves either. */
  identifier: string
  /** Display label for the modal title (typically the serial number). */
  serial: string
  /** Optional machine type for the badge above the form. */
  machineType?: 'RX' | 'RO' | string | null
  /** Current machine status, displayed as a badge. */
  currentStatus?: string
  token: string
  onClose: () => void
  /** Called after the POST /api/reservations succeeds. */
  onCreated: () => void
}

export default function ReserveMachineModal({
  identifier,
  serial,
  machineType,
  currentStatus,
  token,
  onClose,
  onCreated,
}: Props) {
  const [reservedFor, setReservedFor] = useState('')
  // The backend ReservationCreate model only accepts machine_id + reserved_for.
  // We surface a Notes field in the UI but append it onto reserved_for so the
  // admin sees the context on approval, since there is no dedicated column.
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reservedFor.trim()) {
      setErr('Customer / lead name is required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      const trimmedNotes = notes.trim()
      const reservedForBody = trimmedNotes
        ? `${reservedFor.trim()} — ${trimmedNotes}`
        : reservedFor.trim()
      await apiPostAuth(
        '/api/reservations',
        { machine_id: identifier, reserved_for: reservedForBody },
        token,
      )
      onCreated()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rsv-modal-overlay" onClick={onClose}>
      <form
        className="rsv-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="rsv-modal-title">Reserve Machine — {serial}</h3>

        <div className="rsv-modal-meta-row">
          {machineType === 'RX' || machineType === 'RO' ? (
            <span className={`rsv-type-badge rsv-type-${machineType.toLowerCase()}`}>
              {machineType}
            </span>
          ) : null}
          {currentStatus && (
            <span className={`rsv-status rsv-status-${currentStatus}`}>
              {currentStatus}
            </span>
          )}
        </div>

        <p className="rsv-modal-sub">
          The reservation will be <strong>pending</strong> until an admin approves
          it. Once approved, the machine is held for 7 days.
        </p>

        <label className="rsv-field">
          <span>Reserved For *</span>
          <input
            value={reservedFor}
            onChange={(e) => setReservedFor(e.target.value)}
            autoFocus
            placeholder="Customer or lead name"
          />
        </label>

        <label className="rsv-field">
          <span>Notes <em>(optional)</em></span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Any additional notes for the admin"
          />
        </label>

        {err && <div className="rsv-form-error">{err}</div>}

        <div className="rsv-modal-actions">
          <button
            type="button"
            className="rsv-btn rsv-btn-ghost"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="rsv-btn rsv-btn-primary"
            disabled={saving}
          >
            {saving ? 'Submitting…' : 'Submit Reservation'}
          </button>
        </div>
      </form>
    </div>
  )
}
