import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, notifyExpensesChanged } from '../api'
import { CategoryBadge, CategoryPicker, Empty, ErrorNote, Modal, PaymentPicker, Spinner } from '../components/ui'
import { useMeta } from '../hooks'
import type { Payment, Recurring as Rec } from '../types'
import { currentMonth, cx, formatINR, monthLabel, ordinal, shortDate } from '../utils'

export default function Recurring() {
  const { cat, paymentLabel } = useMeta()
  const [items, setItems] = useState<Rec[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Rec | 'new' | null>(null)

  const load = useCallback(() => {
    api.listRecurring().then(setItems).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  async function toggle(r: Rec) {
    try {
      const { id: _id, last_generated_month: _l, next_due: _n, ...body } = r
      await api.updateRecurring(r.id, { ...body, active: !r.active })
      load()
      notifyExpensesChanged()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const monthlyTotal = (items ?? []).filter((r) => r.active).reduce((s, r) => s + r.amount, 0)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Recurring</h1>
          <p className="muted">Rent, EMIs, subscriptions — added to your expenses automatically on their due day.</p>
        </div>
        <button className="btn primary" onClick={() => setEditing('new')}>+ New recurring</button>
      </div>
      <ErrorNote message={error} />
      {!items && !error && <Spinner />}

      {items && (items.length === 0 ? (
        <div className="card">
          <Empty icon="🔁" title="No recurring expenses yet">
            Add things you pay every month and they'll show up on their own.
          </Empty>
        </div>
      ) : (
        <>
          <div className="list-summary card">
            <span>Committed every month</span>
            <b>{formatINR(monthlyTotal)}</b>
          </div>
          <ul className="rec-list">
            {items.map((r) => (
              <li key={r.id} className={cx('card rec', !r.active && 'paused')}>
                <CategoryBadge id={r.category} />
                <div className="rec-main">
                  <b>{r.note || cat(r.category).label}</b>
                  <span className="muted small-text">
                    Every month on the {ordinal(r.day_of_month)}
                    {r.payment_method && ` · ${paymentLabel(r)}`}
                    {r.end_month && ` · until ${monthLabel(r.end_month)}`}
                  </span>
                  <span className="small-text">
                    {r.active
                      ? r.next_due ? <>Next: <b>{shortDate(r.next_due)}</b></> : 'Finished'
                      : 'Paused'}
                  </span>
                </div>
                <div className="rec-side">
                  <b className="tx-amt">{formatINR(r.amount)}</b>
                  <div className="rec-actions">
                    <label className="switch" title={r.active ? 'Pause' : 'Resume'}>
                      <input type="checkbox" checked={r.active} onChange={() => toggle(r)} />
                      <span />
                    </label>
                    <button className="link-btn" onClick={() => setEditing(r)}>Edit</button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      ))}

      {editing && (
        <RecurringForm rec={editing === 'new' ? undefined : editing}
          onClose={(changed) => { setEditing(null); if (changed) { load(); notifyExpensesChanged() } }} />
      )}
    </div>
  )
}

function RecurringForm({ rec, onClose }: { rec?: Rec; onClose: (changed: boolean) => void }) {
  const [amount, setAmount] = useState(rec ? String(rec.amount) : '')
  const [category, setCategory] = useState(rec?.category ?? 'rent')
  const [note, setNote] = useState(rec?.note ?? '')
  const [payment, setPayment] = useState<Payment>({ payment_method: rec?.payment_method ?? 'Google Pay', card_id: rec?.card_id ?? null })
  const [day, setDay] = useState(rec?.day_of_month ?? new Date().getDate())
  const [start, setStart] = useState(rec?.start_month ?? currentMonth())
  const [end, setEnd] = useState(rec?.end_month ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const value = Number(amount)
    if (!value || value <= 0) return setError('Enter an amount greater than zero')
    if (end && end < start) return setError("End month can't be before start month")
    setBusy(true)
    setError(null)
    const body = {
      amount: value, category, note, ...payment, day_of_month: day,
      start_month: start, end_month: end || null, active: rec?.active ?? true,
    }
    try {
      if (rec) await api.updateRecurring(rec.id, body)
      else await api.createRecurring(body)
      onClose(true)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  async function remove() {
    if (!rec || !confirm('Delete this recurring expense? Expenses already added stay in your history.')) return
    setBusy(true)
    try {
      await api.deleteRecurring(rec.id)
      onClose(true)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Modal title={rec ? 'Edit recurring expense' : 'New recurring expense'} onClose={() => onClose(false)} footer={
      <>
        {rec && <button className="btn danger-ghost" onClick={remove} disabled={busy}>Delete</button>}
        <span className="spacer" />
        <button className="btn ghost" onClick={() => onClose(false)} disabled={busy}>Cancel</button>
        <button type="submit" form="rec-form" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </>
    }>
      <form id="rec-form" className="form" onSubmit={submit}>
        <label className="amount-field">
          <span className="sr-only">Amount</span>
          <span className="amount-prefix">₹</span>
          <input autoFocus={!rec} inputMode="decimal" placeholder="0" value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
        </label>
        <label className="field">
          <span className="field-label">Name</span>
          <input value={note} maxLength={200} placeholder="e.g. Flat rent, Netflix, Car EMI" onChange={(e) => setNote(e.target.value)} />
        </label>
        <div className="field">
          <span className="field-label">Category</span>
          <CategoryPicker value={category} onChange={setCategory} />
        </div>
        <div className="row-3">
          <label className="field">
            <span className="field-label">Day of month</span>
            <select value={day} onChange={(e) => setDay(Number(e.target.value))}>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>{ordinal(d)}{d >= 29 ? ' (or last day)' : ''}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Starts</span>
            <input type="month" value={start} onChange={(e) => setStart(e.target.value)} required />
          </label>
          <label className="field">
            <span className="field-label">Ends <span className="muted">(optional)</span></span>
            <input type="month" value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <div className="field">
          <span className="field-label">Paid with</span>
          <PaymentPicker value={payment} onChange={setPayment} />
        </div>
        {rec
          ? <p className="hint">Changes apply from the next occurrence; past entries aren't touched.</p>
          : start < currentMonth() && <p className="hint">Months since {monthLabel(start)} will be filled in too.</p>}
        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}
