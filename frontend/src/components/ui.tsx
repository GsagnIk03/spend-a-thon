import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { PAYMENT_ICONS, useMeta } from '../hooks'
import type { Payment } from '../types'
import CategoryEditor from './CategoryEditor'
import { addMonths, currentMonth, cx, formatINRRound, monthLabel } from '../utils'

export function Modal({ title, onClose, children, footer }: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const all = document.querySelectorAll('.modal-backdrop')
      if (all[all.length - 1] === ref.current) onClose() // only the top-most modal
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])
  // Portal: modals opened from inside another modal's <form> must not nest forms in the DOM.
  return createPortal(
    <div ref={ref} className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}

export function MonthPicker({ month, onChange }: { month: string; onChange: (m: string) => void }) {
  const atCurrent = month >= currentMonth()
  return (
    <div className="month-picker">
      <button className="icon-btn" onClick={() => onChange(addMonths(month, -1))} aria-label="Previous month">‹</button>
      <span className="month-label">{monthLabel(month)}</span>
      <button className="icon-btn" onClick={() => onChange(addMonths(month, 1))} disabled={atCurrent}
        aria-label="Next month">›</button>
    </div>
  )
}

export function CategoryBadge({ id, size = 'md' }: { id: string; size?: 'sm' | 'md' }) {
  const { cat } = useMeta()
  const c = cat(id)
  return (
    <span className={cx('cat-badge', size)} style={{ background: `${c.color}22`, color: c.color }} title={c.label}>
      {c.emoji}
    </span>
  )
}

export function CategoryPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const { categories } = useMeta()
  const [creating, setCreating] = useState(false)
  return (
    <>
      <div className="cat-grid" role="radiogroup" aria-label="Category">
        {categories.map((c) => (
          <button key={c.id} type="button" role="radio" aria-checked={value === c.id}
            className={cx('cat-chip', value === c.id && 'active')}
            style={value === c.id ? { borderColor: c.color, background: `${c.color}1f` } : undefined}
            onClick={() => onChange(c.id)}>
            <span className="cat-chip-emoji">{c.emoji}</span>
            <span className="cat-chip-label">{c.label}</span>
          </button>
        ))}
        <button type="button" className="cat-chip add" onClick={() => setCreating(true)}>
          <span className="cat-chip-emoji">＋</span>
          <span className="cat-chip-label">New</span>
        </button>
      </div>
      {creating && (
        <CategoryEditor onClose={(created) => { setCreating(false); if (created) onChange(created.id) }} />
      )}
    </>
  )
}

export function PaymentPicker({ value, onChange }: { value: Payment; onChange: (p: Payment) => void }) {
  const { paymentMethods, activeCards, card } = useMeta()
  const isCard = value.payment_method === 'Credit card'
  const current = card(value.card_id)
  return (
    <div className="payment-picker">
      <div className="chips">
        {paymentMethods.map((m) => (
          <button key={m} type="button" className={cx('chip', value.payment_method === m && 'active')}
            onClick={() => onChange(value.payment_method === m
              ? { payment_method: null, card_id: null }
              : { payment_method: m, card_id: m === 'Credit card' ? (value.card_id ?? activeCards[0]?.id ?? null) : null })}>
            <span aria-hidden>{PAYMENT_ICONS[m] ?? '•'}</span> {m}
          </button>
        ))}
      </div>
      {isCard && (
        activeCards.length === 0 && !current ? (
          <p className="hint">No cards yet — <Link to="/cards">add your credit cards</Link> to track their balance.</p>
        ) : (
          <div className="card-choices">
            {[...activeCards, ...(current?.archived ? [current] : [])].map((c) => (
              <button key={c.id} type="button"
                className={cx('card-choice', value.card_id === c.id && 'active')}
                style={{ '--card-color': c.color ?? '#0f766e' } as CSSProperties}
                onClick={() => onChange({ payment_method: 'Credit card', card_id: c.id })}>
                <span className="card-choice-name">{c.name}{c.last4 && <span className="muted"> ••{c.last4}</span>}</span>
                <span className="card-choice-bal">{formatINRRound(c.available)} available</span>
              </button>
            ))}
          </div>
        )
      )}
    </div>
  )
}

export function Chips({ options, value, onChange, allowNone = true }: {
  options: string[]
  value: string | null
  onChange: (v: string | null) => void
  allowNone?: boolean
}) {
  return (
    <div className="chips">
      {options.map((o) => (
        <button key={o} type="button" className={cx('chip', value === o && 'active')}
          onClick={() => onChange(value === o && allowNone ? null : o)}>
          {o}
        </button>
      ))}
    </div>
  )
}

export function ProgressBar({ value, max, color }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const over = value > max
  const warn = !over && pct >= 85
  return (
    <div className="progress" aria-label={`${Math.round((value / (max || 1)) * 100)}% used`}>
      <div className={cx('progress-fill', over && 'over', warn && 'warn')}
        style={{ width: `${pct}%`, background: over || warn ? undefined : color }} />
    </div>
  )
}

export function Empty({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {children && <div className="empty-body">{children}</div>}
    </div>
  )
}

export function Spinner() {
  return <div className="spinner" aria-label="Loading" />
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null
  return <div className="error-note" role="alert">{message}</div>
}
