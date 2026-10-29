import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'
import ExpenseForm from '../components/ExpenseForm'
import { CategoryBadge, Empty, ErrorNote, MonthPicker, ProgressBar, Spinner } from '../components/ui'
import { PAYMENT_ICONS, useExpensesChanged, useMeta } from '../hooks'
import type { Expense, Summary } from '../types'
import { currentMonth, cx, formatCompact, formatINR, formatINRRound, shortDate, shortMonth } from '../utils'

const tooltipStyle = {
  contentStyle: {
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
    color: 'var(--text)', fontSize: 13,
  },
  cursor: { fill: 'var(--hover)' },
}

export default function Dashboard() {
  const { cat, paymentLabel } = useMeta()
  const [month, setMonth] = useState(currentMonth())
  const [data, setData] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Expense | null>(null)

  const load = useCallback(() => {
    setError(null)
    api.summary(month).then(setData).catch((e) => setError(e.message))
  }, [month])
  useEffect(() => { setData(null); load() }, [load])
  useExpensesChanged(load)

  const isCurrent = month === currentMonth()
  const change = data && data.previous_total > 0 ? ((data.total - data.previous_total) / data.previous_total) * 100 : null
  const daysElapsed = data ? (isCurrent ? new Date().getDate() : data.by_day.length) : 1
  const budgetLeft = data?.budget_total != null ? data.budget_total - data.total : null
  const spentCats = data?.by_category.filter((c) => c.spent > 0) ?? []
  const budgeted = data?.by_category.filter((c) => c.budget != null) ?? []
  const dayLabels = (d: string) => String(Number(d.slice(8)))

  return (
    <div className="page">
      <div className="page-head">
        <h1>Dashboard</h1>
        <MonthPicker month={month} onChange={setMonth} />
      </div>
      <ErrorNote message={error} />
      {!data && !error && <Spinner />}

      {data && (
        <>
          <section className="stats">
            <div className="stat hero">
              <span className="stat-label">Spent in {shortMonth(month)}</span>
              <span className="stat-value">{formatINR(data.total)}</span>
              <span className="stat-sub">{data.count} expense{data.count === 1 ? '' : 's'}</span>
            </div>
            <div className="stat">
              <span className="stat-label">vs last month</span>
              <span className={cx('stat-value', change != null && (change > 0 ? 'up' : 'down'))}>
                {change == null ? '—' : `${change > 0 ? '▲' : '▼'} ${Math.abs(change).toFixed(0)}%`}
              </span>
              <span className="stat-sub">{formatINRRound(data.previous_total)} last month</span>
            </div>
            <div className="stat">
              <span className="stat-label">Budget left</span>
              {budgetLeft == null ? (
                <>
                  <span className="stat-value muted">—</span>
                  <Link to="/budgets" className="stat-sub link">Set budgets →</Link>
                </>
              ) : (
                <>
                  <span className={cx('stat-value', budgetLeft < 0 && 'up')}>
                    {budgetLeft < 0 ? `-${formatINRRound(-budgetLeft)}` : formatINRRound(budgetLeft)}
                  </span>
                  <ProgressBar value={data.total} max={data.budget_total ?? 0} />
                </>
              )}
            </div>
            <div className="stat">
              <span className="stat-label">Daily average</span>
              <span className="stat-value">{formatINRRound(data.total / Math.max(1, daysElapsed))}</span>
              <span className="stat-sub">over {daysElapsed} day{daysElapsed === 1 ? '' : 's'}</span>
            </div>
          </section>

          {data.count === 0 ? (
            <div className="card">
              <Empty icon="🪙" title={`No expenses in ${shortMonth(month)} yet`}>
                Tap <b>Add expense</b> to log your first one.
              </Empty>
            </div>
          ) : (
            <div className="grid-2">
              <section className="card">
                <h2 className="card-title">Where it went</h2>
                <div className="donut-wrap">
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={spentCats} dataKey="spent" nameKey="category" innerRadius={62} outerRadius={95}
                        paddingAngle={2} stroke="none">
                        {spentCats.map((c) => <Cell key={c.category} fill={cat(c.category).color} />)}
                      </Pie>
                      <Tooltip {...tooltipStyle}
                        formatter={(v: number, n: string) => [formatINR(v), cat(n).label]} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="donut-center">
                    <span className="muted small-text">Total</span>
                    <b>{formatCompact(data.total)}</b>
                  </div>
                </div>
                <ul className="legend">
                  {spentCats.map((c) => (
                    <li key={c.category}>
                      <span className="dot" style={{ background: cat(c.category).color }} />
                      <span className="legend-label">{cat(c.category).emoji} {cat(c.category).label}</span>
                      <span className="legend-pct muted">{((c.spent / data.total) * 100).toFixed(0)}%</span>
                      <span className="legend-amt">{formatINRRound(c.spent)}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="card">
                <h2 className="card-title">Day by day</h2>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.by_day} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="date" tickFormatter={dayLabels} tick={{ fontSize: 11, fill: 'var(--muted)' }}
                      interval="preserveStartEnd" tickLine={false} axisLine={false} minTickGap={8} />
                    <YAxis tickFormatter={formatCompact} tick={{ fontSize: 11, fill: 'var(--muted)' }}
                      tickLine={false} axisLine={false} width={52} />
                    <Tooltip {...tooltipStyle} labelFormatter={(d: string) => shortDate(d)}
                      formatter={(v: number) => [formatINR(v), 'Spent']} />
                    <Bar dataKey="total" fill="var(--accent)" radius={[4, 4, 0, 0]} maxBarSize={18} />
                  </BarChart>
                </ResponsiveContainer>

                <h2 className="card-title spaced">Last 6 months</h2>
                <ResponsiveContainer width="100%" height={170}>
                  <BarChart data={data.trend} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="month" tickFormatter={shortMonth} tick={{ fontSize: 12, fill: 'var(--muted)' }}
                      tickLine={false} axisLine={false} />
                    <YAxis tickFormatter={formatCompact} tick={{ fontSize: 11, fill: 'var(--muted)' }}
                      tickLine={false} axisLine={false} width={52} />
                    <Tooltip {...tooltipStyle} labelFormatter={(m: string) => `${shortMonth(m)} ${m.slice(0, 4)}`}
                      formatter={(v: number) => [formatINR(v), 'Spent']} />
                    <Bar dataKey="total" radius={[4, 4, 0, 0]} maxBarSize={36}>
                      {data.trend.map((t) => (
                        <Cell key={t.month} fill={t.month === month ? 'var(--accent)' : 'var(--accent-soft)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </section>

              {budgeted.length > 0 && (
                <section className="card">
                  <div className="card-title-row">
                    <h2 className="card-title">Budgets</h2>
                    <Link to="/budgets" className="link small-text">Edit</Link>
                  </div>
                  <ul className="budget-list">
                    {budgeted.map((b) => {
                      const left = (b.budget ?? 0) - b.spent
                      return (
                        <li key={b.category}>
                          <div className="budget-line">
                            <span>{cat(b.category).emoji} {cat(b.category).label}</span>
                            <span className={cx('small-text', left < 0 ? 'text-danger' : 'muted')}>
                              {left < 0 ? `${formatINRRound(-left)} over` : `${formatINRRound(left)} left`}
                            </span>
                          </div>
                          <ProgressBar value={b.spent} max={b.budget ?? 0} color={cat(b.category).color} />
                          <div className="budget-nums muted small-text">
                            {formatINRRound(b.spent)} of {formatINRRound(b.budget ?? 0)}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              )}

              <section className="card">
                <div className="card-title-row">
                  <h2 className="card-title">How you paid</h2>
                  <Link to="/insights" className="link small-text">Details</Link>
                </div>
                <ul className="pay-list">
                  {data.by_payment.map((p) => (
                    <li key={p.key}>
                      <span className="pay-icon" style={p.card_id ? { background: p.color ?? 'var(--accent)', color: '#fff' } : undefined}>
                        {PAYMENT_ICONS[p.method] ?? '•'}
                      </span>
                      <span className="grow">
                        <b>{p.label}</b>
                        <span className="muted small-text"> · {p.count} txn{p.count === 1 ? '' : 's'}</span>
                        <span className="share-bar thin">
                          <span style={{ width: `${(p.total / data.total) * 100}%`, background: p.color ?? 'var(--accent)' }} />
                        </span>
                      </span>
                      <span className="tx-amt">{formatINRRound(p.total)}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="card">
                <div className="card-title-row">
                  <h2 className="card-title">Biggest expenses</h2>
                  <Link to="/expenses" className="link small-text">See all</Link>
                </div>
                <ul className="tx-list">
                  {data.top.map((e) => (
                    <li key={e.id}>
                      <button className="tx" onClick={() => setEditing(e)}>
                        <CategoryBadge id={e.category} />
                        <span className="tx-main">
                          <span className="tx-title">{e.note || cat(e.category).label}</span>
                          <span className="tx-sub">{shortDate(e.date)} · {cat(e.category).label}{e.payment_method && ` · ${paymentLabel(e)}`}</span>
                        </span>
                        <span className="tx-amt">{formatINR(e.amount)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </>
      )}
      {editing && <ExpenseForm expense={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}
