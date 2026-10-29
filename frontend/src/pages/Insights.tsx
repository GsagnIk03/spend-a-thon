import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { CategoryManager } from '../components/CategoryEditor'
import ExpenseForm from '../components/ExpenseForm'
import { CategoryBadge, Empty, ErrorNote, Spinner } from '../components/ui'
import { PAYMENT_ICONS, useExpensesChanged, useMeta } from '../hooks'
import type { Expense, Insights as Data } from '../types'
import {
  addMonths, currentMonth, cx, formatCompact, formatINR, formatINRRound, monthLabel, shortDate, shortMonth,
} from '../utils'

type Preset = '1' | '3' | '6' | 'ytd' | '12' | 'custom'
const PRESETS: { id: Preset; label: string }[] = [
  { id: '1', label: 'This month' },
  { id: '3', label: '3 months' },
  { id: '6', label: '6 months' },
  { id: 'ytd', label: 'This year' },
  { id: '12', label: '12 months' },
  { id: 'custom', label: 'Custom' },
]

function rangeFor(p: Preset): [string, string] {
  const end = currentMonth()
  if (p === 'ytd') return [`${end.slice(0, 4)}-01`, end]
  const n = p === 'custom' ? 1 : Number(p)
  return [addMonths(end, -(n - 1)), end]
}

const tooltip = {
  contentStyle: {
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', fontSize: 13,
  },
  cursor: { fill: 'var(--hover)' },
}

function MiniBars({ data, color }: { data: { month: string; total: number }[]; color: string }) {
  return (
    <ResponsiveContainer width="100%" height={150}>
      <BarChart data={data} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="month" tickFormatter={shortMonth} tick={{ fontSize: 11, fill: 'var(--muted)' }}
          tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis tickFormatter={formatCompact} tick={{ fontSize: 11, fill: 'var(--muted)' }} tickLine={false}
          axisLine={false} width={50} />
        <Tooltip {...tooltip} labelFormatter={(m: string) => monthLabel(m)} formatter={(v: number) => [formatINR(v), 'Spent']} />
        <Bar dataKey="total" fill={color} radius={[4, 4, 0, 0]} maxBarSize={32} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function Insights() {
  const { cat, paymentLabel } = useMeta()
  const [preset, setPreset] = useState<Preset>('3')
  const [[start, end], setRange] = useState<[string, string]>(rangeFor('3'))
  const [tab, setTab] = useState<'category' | 'payment'>('category')
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [rows, setRows] = useState<Expense[] | null>(null)
  const [editing, setEditing] = useState<Expense | null>(null)
  const [managing, setManaging] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api.insights(start, end).then(setData).catch((e) => setError(e.message))
  }, [start, end])
  useEffect(() => { setData(null); setOpen(null); load() }, [load])

  const loadRows = useCallback(() => {
    if (!open) return setRows(null)
    const [kind, key] = open.split('|')
    api.listExpenses(kind === 'cat' ? { start, end, category: key } : { start, end, payment: key })
      .then(setRows).catch((e) => setError(e.message))
  }, [open, start, end])
  useEffect(() => { setRows(null); loadRows() }, [loadRows])

  const reloadAll = useCallback(() => { load(); loadRows() }, [load, loadRows])
  useExpensesChanged(reloadAll)

  function choose(p: Preset) {
    setPreset(p)
    if (p !== 'custom') setRange(rangeFor(p))
  }

  const toggle = (id: string) => setOpen((o) => (o === id ? null : id))
  const periodLabel = start === end ? monthLabel(start) : `${shortMonth(start)} ${start.slice(0, 4)} – ${shortMonth(end)} ${end.slice(0, 4)}`

  const drill = rows && (
    rows.length === 0 ? <p className="muted small-text drill-empty">No transactions.</p> : (
      <ul className="tx-list drill">
        {rows.map((e) => (
          <li key={e.id}>
            <button className="tx" onClick={() => setEditing(e)}>
              <CategoryBadge id={e.category} size="sm" />
              <span className="tx-main">
                <span className="tx-title">{e.note || cat(e.category).label}</span>
                <span className="tx-sub">{shortDate(e.date)} · {paymentLabel(e) || 'No method'}</span>
              </span>
              <span className="tx-amt">{formatINR(e.amount)}</span>
            </button>
          </li>
        ))}
      </ul>
    )
  )

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Insights</h1>
          <p className="muted">{periodLabel}</p>
        </div>
        <button className="btn ghost" onClick={() => setManaging(true)}>🏷️ Categories</button>
      </div>

      <div className="period-bar">
        <div className="chips">
          {PRESETS.map((p) => (
            <button key={p.id} className={cx('chip', preset === p.id && 'active')} onClick={() => choose(p.id)}>{p.label}</button>
          ))}
        </div>
        {preset === 'custom' && (
          <div className="custom-range">
            <input type="month" value={start} max={end} onChange={(e) => e.target.value && setRange([e.target.value, end])} />
            <span className="muted">to</span>
            <input type="month" value={end} min={start} max={currentMonth()}
              onChange={(e) => e.target.value && setRange([start, e.target.value])} />
          </div>
        )}
      </div>

      <ErrorNote message={error} />
      {!data && !error && <Spinner />}

      {data && (
        data.count === 0 ? (
          <div className="card"><Empty icon="🔍" title="No expenses in this period" /></div>
        ) : (
          <>
            <section className="stats three">
              <div className="stat hero">
                <span className="stat-label">Total spent</span>
                <span className="stat-value">{formatINR(data.total)}</span>
                <span className="stat-sub">{data.count} transactions</span>
              </div>
              <div className="stat">
                <span className="stat-label">Per month</span>
                <span className="stat-value">{formatINRRound(data.monthly_average)}</span>
                <span className="stat-sub">average over {data.months} month{data.months > 1 ? 's' : ''}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Average transaction</span>
                <span className="stat-value">{formatINRRound(data.total / data.count)}</span>
                <span className="stat-sub">{(data.count / data.months).toFixed(0)} per month</span>
              </div>
            </section>

            <div className="seg wide">
              <button className={tab === 'category' ? 'active' : ''} onClick={() => { setTab('category'); setOpen(null) }}>
                By category
              </button>
              <button className={tab === 'payment' ? 'active' : ''} onClick={() => { setTab('payment'); setOpen(null) }}>
                By payment method
              </button>
            </div>

            {tab === 'category' && (
              <section className="card flush">
                <ul className="breakdown">
                  {data.by_category.map((c) => {
                    const meta = cat(c.category)
                    const id = `cat|${c.category}`
                    return (
                      <li key={c.category} className={cx(open === id && 'open')}>
                        <button className="breakdown-row" onClick={() => toggle(id)} aria-expanded={open === id}>
                          <CategoryBadge id={c.category} />
                          <span className="breakdown-main">
                            <span className="breakdown-top">
                              <b>{meta.label}</b>
                              <b className="tx-amt">{formatINR(c.total)}</b>
                            </span>
                            <span className="share-bar"><span style={{ width: `${c.share}%`, background: meta.color }} /></span>
                            <span className="breakdown-sub muted small-text">
                              <span>{c.count} × · avg {formatINRRound(c.average)}</span>
                              <span>{c.share}%{data.months > 1 && ` · ${formatINRRound(c.total / data.months)}/mo`}</span>
                            </span>
                          </span>
                        </button>
                        {open === id && (
                          <div className="breakdown-detail">
                            {data.months > 1 && <MiniBars data={c.monthly} color={meta.color} />}
                            {drill ?? <Spinner />}
                          </div>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </section>
            )}

            {tab === 'payment' && (
              <>
                <section className="method-tiles">
                  {data.by_method.map((m) => (
                    <div key={m.method} className="method-tile">
                      <span className="method-icon">{PAYMENT_ICONS[m.method] ?? '•'}</span>
                      <span className="muted small-text">{m.method}</span>
                      <b>{formatINRRound(m.total)}</b>
                      <span className="muted small-text">{m.count} transaction{m.count === 1 ? '' : 's'}</span>
                    </div>
                  ))}
                </section>
                <section className="card flush">
                  <ul className="breakdown">
                    {data.by_payment.map((p) => {
                      const id = `pay|${p.key}`
                      const color = p.color ?? 'var(--accent)'
                      return (
                        <li key={p.key} className={cx(open === id && 'open')}>
                          <button className="breakdown-row" onClick={() => toggle(id)} aria-expanded={open === id}>
                            <span className="cat-badge md pay-badge" style={p.card_id ? { background: color, color: '#fff' } : undefined}>
                              {PAYMENT_ICONS[p.method] ?? '•'}
                            </span>
                            <span className="breakdown-main">
                              <span className="breakdown-top">
                                <b>{p.label}{p.card_id && <span className="muted small-text"> · credit card</span>}</b>
                                <b className="tx-amt">{formatINR(p.total)}</b>
                              </span>
                              <span className="share-bar"><span style={{ width: `${p.share ?? 0}%`, background: color }} /></span>
                              <span className="breakdown-sub muted small-text">
                                <span>{p.count} transaction{p.count === 1 ? '' : 's'}</span>
                                <span>{p.share}%</span>
                              </span>
                            </span>
                          </button>
                          {open === id && (
                            <div className="breakdown-detail">
                              {data.months > 1 && p.monthly && <MiniBars data={p.monthly} color={color} />}
                              {drill ?? <Spinner />}
                            </div>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </section>
              </>
            )}

            {data.months > 1 && (
              <section className="card">
                <h2 className="card-title">Month by month</h2>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={data.monthly} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="month" tickFormatter={shortMonth} tick={{ fontSize: 12, fill: 'var(--muted)' }}
                      tickLine={false} axisLine={false} />
                    <YAxis tickFormatter={formatCompact} tick={{ fontSize: 11, fill: 'var(--muted)' }}
                      tickLine={false} axisLine={false} width={52} />
                    <Tooltip {...tooltip} labelFormatter={(m: string) => monthLabel(m)}
                      formatter={(v: number) => [formatINR(v), 'Spent']} />
                    <Bar dataKey="total" radius={[4, 4, 0, 0]} maxBarSize={40}>
                      {data.monthly.map((m) => (
                        <Cell key={m.month} fill={m.total > data.monthly_average ? 'var(--accent)' : 'var(--accent-soft)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="hint">Darker bars are months above your average.</p>
              </section>
            )}
          </>
        )
      )}

      {editing && <ExpenseForm expense={editing} onClose={() => setEditing(null)} />}
      {managing && <CategoryManager onClose={() => setManaging(false)} />}
    </div>
  )
}
