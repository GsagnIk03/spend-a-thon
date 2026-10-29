import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { CategoryManager } from '../components/CategoryEditor'
import { ErrorNote, ProgressBar, Spinner } from '../components/ui'
import { useExpensesChanged, useMeta } from '../hooks'
import { currentMonth, cx, formatINRRound, monthLabel } from '../utils'

export default function Budgets() {
  const { categories, cat } = useMeta()
  const month = currentMonth()
  const [values, setValues] = useState<Record<string, string> | null>(null)
  const [saved, setSaved] = useState<Record<string, number>>({})
  const [spent, setSpent] = useState<Record<string, number>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState(false)
  const [managing, setManaging] = useState(false)

  const loadSpent = useCallback(() => {
    api.summary(month)
      .then((s) => setSpent(Object.fromEntries(s.by_category.map((c) => [c.category, c.spent]))))
      .catch(() => {})
  }, [month])

  useEffect(() => {
    api.getBudgets()
      .then(({ budgets }) => {
        setSaved(budgets)
        setValues(Object.fromEntries(Object.entries(budgets).map(([k, v]) => [k, String(v)])))
      })
      .catch((e) => setError(e.message))
    loadSpent()
  }, [loadSpent])
  useExpensesChanged(loadSpent)

  const dirty = values != null && categories.some((c) => {
    const v = values[c.id] ?? ''
    const s = saved[c.id]
    return (v === '' ? undefined : Number(v)) !== s
  })

  async function save() {
    if (!values) return
    const payload: Record<string, number | null> = {}
    for (const c of categories) {
      const raw = (values[c.id] ?? '').trim()
      if (raw === '') { if (saved[c.id] != null) payload[c.id] = null; continue }
      const n = Number(raw)
      if (!Number.isFinite(n) || n < 0) return setError(`Budget for ${c.label} must be a positive number`)
      payload[c.id] = n === 0 ? null : n
    }
    setBusy(true)
    setError(null)
    try {
      const { budgets } = await api.saveBudgets(payload)
      setSaved(budgets)
      setValues(Object.fromEntries(Object.entries(budgets).map(([k, v]) => [k, String(v)])))
      setFlash(true)
      setTimeout(() => setFlash(false), 1800)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const totalBudget = Object.values(saved).reduce((a, b) => a + b, 0)
  const totalSpentBudgeted = Object.keys(saved).reduce((a, k) => a + (spent[k] ?? 0), 0)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Budgets</h1>
          <p className="muted">Monthly limits per category. Progress shows {monthLabel(month)}.</p>
        </div>
        <div className="btn-row">
          <button className="btn ghost" onClick={() => setManaging(true)}>🏷️ Categories</button>
          <button className={cx('btn primary', flash && 'success')} onClick={save} disabled={busy || !dirty}>
            {flash ? '✓ Saved' : busy ? 'Saving…' : 'Save budgets'}
          </button>
        </div>
      </div>
      <ErrorNote message={error} />
      {!values && !error && <Spinner />}

      {values && (
        <>
          {totalBudget > 0 && (
            <div className="card budget-total">
              <div className="budget-line">
                <b>Total budget</b>
                <span>{formatINRRound(totalSpentBudgeted)} of {formatINRRound(totalBudget)}</span>
              </div>
              <ProgressBar value={totalSpentBudgeted} max={totalBudget} />
            </div>
          )}
          <div className="card flush">
            <ul className="budget-edit">
              {categories.map((c) => {
                const limit = saved[c.id]
                const s = spent[c.id] ?? 0
                return (
                  <li key={c.id}>
                    <span className="cat-badge md" style={{ background: `${c.color}22` }}>{c.emoji}</span>
                    <div className="budget-edit-main">
                      <div className="budget-line">
                        <span>{c.label}</span>
                        <span className="muted small-text">
                          {formatINRRound(s)} spent{limit ? ` · ${s > limit ? `${formatINRRound(s - limit)} over` : `${formatINRRound(limit - s)} left`}` : ''}
                        </span>
                      </div>
                      {limit ? <ProgressBar value={s} max={limit} color={cat(c.id).color} /> : null}
                    </div>
                    <label className="budget-input">
                      <span>₹</span>
                      <input inputMode="decimal" placeholder="No limit" value={values[c.id] ?? ''}
                        aria-label={`${c.label} monthly budget`}
                        onChange={(e) => setValues({ ...values, [c.id]: e.target.value.replace(/[^\d.]/g, '') })} />
                    </label>
                  </li>
                )
              })}
            </ul>
          </div>
        </>
      )}
      {managing && <CategoryManager onClose={() => setManaging(false)} />}
    </div>
  )
}
