import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import ExpenseForm from '../components/ExpenseForm'
import { CategoryBadge, Empty, ErrorNote, Modal, MonthPicker, Spinner } from '../components/ui'
import { useExpensesChanged, useMeta } from '../hooks'
import type { Expense } from '../types'
import { addMonths, currentMonth, dayHeading, formatINR } from '../utils'

export default function Expenses() {
  const { categories, cat, paymentMethods, cards, paymentLabel } = useMeta()
  const [month, setMonth] = useState(currentMonth())
  const [category, setCategory] = useState('')
  const [payment, setPayment] = useState('')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<Expense[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Expense | null>(null)
  const [exporting, setExporting] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api.listExpenses({ month, category, payment }).then(setItems).catch((e) => setError(e.message))
  }, [month, category, payment])
  useEffect(() => { setItems(null); load() }, [load])
  useExpensesChanged(load)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!items || !q) return items ?? []
    return items.filter((e) =>
      e.note.toLowerCase().includes(q) ||
      cat(e.category).label.toLowerCase().includes(q) ||
      paymentLabel(e).toLowerCase().includes(q) ||
      String(e.amount).includes(q))
  }, [items, search, cat, paymentLabel])

  const groups = useMemo(() => {
    const m = new Map<string, Expense[]>()
    filtered.forEach((e) => m.set(e.date, [...(m.get(e.date) ?? []), e]))
    return [...m.entries()]
  }, [filtered])

  const total = filtered.reduce((s, e) => s + e.amount, 0)

  return (
    <div className="page">
      <div className="page-head">
        <h1>Expenses</h1>
        <MonthPicker month={month} onChange={setMonth} />
      </div>

      <div className="toolbar">
        <input className="search" type="search" placeholder="Search notes, categories…" value={search}
          onChange={(e) => setSearch(e.target.value)} />
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Filter by category">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.emoji} {c.label}</option>)}
        </select>
        <select value={payment} onChange={(e) => setPayment(e.target.value)} aria-label="Filter by payment method">
          <option value="">All payment methods</option>
          {paymentMethods.filter((m) => m !== 'Credit card').map((m) => <option key={m} value={m}>{m}</option>)}
          {cards.length > 0 && (
            <optgroup label="Credit cards">
              {cards.map((c) => <option key={c.id} value={`card:${c.id}`}>💳 {c.name}</option>)}
            </optgroup>
          )}
        </select>
        <button className="btn ghost" onClick={() => setExporting(true)}>⬇ Export CSV</button>
      </div>

      <ErrorNote message={error} />
      {!items && !error && <Spinner />}

      {items && (
        <div className="card flush">
          <div className="list-summary">
            <span>{filtered.length} expense{filtered.length === 1 ? '' : 's'}</span>
            <b>{formatINR(total)}</b>
          </div>
          {groups.length === 0 ? (
            <Empty icon="🧾" title={search || category || payment ? 'Nothing matches' : 'No expenses this month'}>
              {search || category || payment ? 'Try a different search or filter.' : 'Use Add expense to log one.'}
            </Empty>
          ) : (
            groups.map(([date, list]) => (
              <div key={date} className="day-group">
                <div className="day-head">
                  <span>{dayHeading(date)}</span>
                  <span>{formatINR(list.reduce((s, e) => s + e.amount, 0))}</span>
                </div>
                <ul className="tx-list">
                  {list.map((e) => (
                    <li key={e.id}>
                      <button className="tx" onClick={() => setEditing(e)}>
                        <CategoryBadge id={e.category} />
                        <span className="tx-main">
                          <span className="tx-title">{e.note || cat(e.category).label}</span>
                          <span className="tx-sub">
                            {cat(e.category).label}
                            {e.payment_method && ` · ${paymentLabel(e)}`}
                            {e.recurring_id && <span className="tag">🔁 recurring</span>}
                            {e.loan_id && <span className="tag">🏦 EMI</span>}
                          </span>
                        </span>
                        <span className="tx-amt">{formatINR(e.amount)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      )}

      {editing && <ExpenseForm expense={editing} onClose={() => setEditing(null)} />}
      {exporting && <ExportDialog month={month} onClose={() => setExporting(false)} />}
    </div>
  )
}

function ExportDialog({ month, onClose }: { month: string; onClose: () => void }) {
  const [start, setStart] = useState(month)
  const [end, setEnd] = useState(month)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function go() {
    if (!start || !end) return setError('Pick both months')
    if (start > end) return setError('"From" must not be after "To"')
    setBusy(true)
    setError(null)
    try {
      await api.exportCsv(start, end)
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  const preset = (n: number) => { setStart(addMonths(month, -(n - 1))); setEnd(month) }

  return (
    <Modal title="Export to CSV" onClose={onClose} footer={
      <>
        <span className="spacer" />
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={go} disabled={busy}>{busy ? 'Preparing…' : 'Download'}</button>
      </>
    }>
      <div className="form">
        <div className="chips">
          <button type="button" className="chip" onClick={() => preset(1)}>This month</button>
          <button type="button" className="chip" onClick={() => preset(3)}>Last 3 months</button>
          <button type="button" className="chip" onClick={() => preset(12)}>Last 12 months</button>
        </div>
        <div className="row-2">
          <label className="field">
            <span className="field-label">From</span>
            <input type="month" value={start} max={currentMonth()} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">To</span>
            <input type="month" value={end} max={currentMonth()} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <p className="hint">Opens in Excel or Google Sheets. Up to 24 months at a time.</p>
        <ErrorNote message={error} />
      </div>
    </Modal>
  )
}
