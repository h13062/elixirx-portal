import { useState, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import './ConfirmModal.css'

interface Props {
  title: string
  message: ReactNode
  warning?: string | null
  confirmLabel: string
  confirmKind?: 'danger' | 'primary'
  /** Async-aware: if it returns a promise, the button shows a "..." state until it resolves. */
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}

export default function ConfirmModal({
  title,
  message,
  warning,
  confirmLabel,
  confirmKind = 'danger',
  onConfirm,
  onCancel,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const handleConfirm = async () => {
    setBusy(true)
    setErr(null)
    try {
      await onConfirm()
    } catch (e) {
      setErr((e as Error).message || 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="cm-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel()
      }}
    >
      <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="cm-title">{title}</h3>
        <div className="cm-message">{message}</div>
        {warning && (
          <div className="cm-warning">
            <AlertTriangle size={14} /> {warning}
          </div>
        )}
        {err && <div className="cm-error">{err}</div>}
        <div className="cm-actions">
          <button
            className="cm-btn cm-btn-cancel"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            className={`cm-btn cm-btn-${confirmKind}`}
            onClick={handleConfirm}
            disabled={busy}
          >
            {busy ? `${confirmLabel}…` : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
