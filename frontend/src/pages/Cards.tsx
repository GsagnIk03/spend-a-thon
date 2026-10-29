import { useCallback, useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { api, notifyExpensesChanged } from '../api'
import ExpenseForm from '../components/ExpenseForm'
import { CategoryBadge, Empty, ErrorNote, Modal, Spinner } from '../components/ui'
import { useExpensesChanged, useMeta } from '../hooks'
import type { Card, CardInput, CardPayment, Expense } from '../types'
import { addMonths, currentMonth, cx, formatINR, formatINRRound, ordinal, shortDate, todayISO } from '../utils'

const COLORS = ['#0f766e', '#1e3a8a', '#7c2d12', '#581c87', '#111827', '#9f1239', '#155e75', '#3f6212']

function nextDay(day: number | null): string | null {
  if (!day) return null
  const t = new Date()
  const cand = new Date(t.getFullYear(), t.getMonth(), day)
  if (cand < new Date(t.getFullYear(), t.getMonth(), t.getDate())) cand.setMonth(cand.getMonth() + 1)
  return `${cand.getDate()} ${cand.toLocaleString('en-IN', { month: 'short' })}`
}

export function CardVisual({ card, onClick, selected }: { card: Card; onClick?: () => void; selected?: boolean }) {
  const util = card.utilization ?? 0
  return (
    <button type="button" className={cx('credit-card', selected && 'selected', card.archived && 'archived')}
      style={{ '--card-color': card.color ?? '#0f766e' } as CSSProperties} onClick={onClick}>
      <div className="cc-top">
        <span className="cc-bank">{card.bank || 'Credit card'}</span>
        <span className="cc-chip" aria-hidden />
      </div>
      <div className="cc-name">{card.name}</div>
      <div className="cc-num">•••• •••• •••• {card.last4 || '····'}</div>
      <div className="cc-bottom">
        <div>
          <span className="cc-label">Available</span>
          <span className="cc-avail">{formatINRRound(card.available)}</span>
        </div>
        <div className="cc-right">
          <span className="cc-label">Limit</span>
          <span>{formatINRRound(card.credit_limit)}</span>
        </div>
      </div>
      <div className="cc-util"><span style={{ width: `${Math.min(100, Math.max(0, util))}%` }} /></div>
    </button>
  )
}

export default function Cards() {
  const { reload: reloadMeta, cat } = useMeta()
  const [cards, setCards] = useState<Card[] | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Card | 'new' | null>(null)
  const [paying, setPaying] = useState<Card | null>(null)
  const [syncing, setSyncing] = useState<Card | null>(null)
  const [txns, setTxns] = useState<Expense[] | null>(null)
  const [payments, setPayments] = useState<CardPayment[] | null>(null)
  const [editingTx, setEditingTx] = useState<Expense | null>(null)

  const load = useCallback(() => {
    api.listCards(showArchived).then((cs) => {
      setCards(cs)
      setSelected((s) => (s && cs.some((c) => c.id === s) ? s : cs[0]?.id ?? null))
    }).catch((e) => setError(e.message))
  }, [showArchived])
  useEffect(load, [load])

  const loadDetail = useCallback(() => {
    if (!selected) return
    const end = currentMonth()
    api.listExpenses({ start: addMonths(end, -2), end, payment: `card:${selected}` }).then(setTxns).catch(() => setTxns([]))
    api.cardPayments(selected).then(setPayments).catch(() => setPayments([]))
  }, [selected])
  useEffect(() => { setTxns(null); setPayments(null); loadDetail() }, [loadDetail])

  const refresh = useCallback(() => { load(); loadDetail() }, [load, loadDetail])
  useExpensesChanged(refresh)
  const afterChange = () => { refresh(); reloadMeta() }

  const card = cards?.find((c) => c.id === selected) ?? null
  const active = (cards ?? []).filter((c) => !c.archived)
  const totals = active.reduce((a, c) => ({ limit: a.limit + c.credit_limit, available: a.available + c.available }),
    { limit: 0, available: 0 })

  async function removePayment(p: CardPayment) {
    if (!card || !confirm(`Remove this ${p.kind} of ${formatINR(p.amount)}? The available balance will go down again.`)) return
    try { await api.deleteCardPayment(card.id, p.id); afterChange() } catch (e) { setError((e as Error).message) }
  }

  async function archive(c: Card) {
    if (!confirm(`Remove ${c.name}? Past expenses keep showing it; you can restore it later.`)) return
    try { await api.archiveCard(c.id); afterChange() } catch (e) { setError((e as Error).message) }
  }

  async function restore(c: Card) {
    try { await api.restoreCard(c.id); afterChange() } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Credit cards</h1>
          <p className="muted">Spends on a card reduce its available balance automatically; bill payments add it back.</p>
        </div>
        <button className="btn primary" onClick={() => setEditing('new')}>+ Add card</button>
      </div>
      <ErrorNote message={error} />
      {!cards && !error && <Spinner />}

      {cards && (cards.length === 0 ? (
        <div className="card">
          <Empty icon="💳" title="No credit cards yet">
            Add your cards with their limit and current available balance. Then pick the card when you log a spend.
          </Empty>
        </div>
      ) : (
        <>
          {active.length > 1 && (
            <section className="stats three">
              <div className="stat">
                <span className="stat-label">Total limit</span>
                <span className="stat-value">{formatINRRound(totals.limit)}</span>
                <span className="stat-sub">{active.length} cards</span>
              </div>
              <div className="stat">
                <span className="stat-label">Available</span>
                <span className="stat-value">{formatINRRound(totals.available)}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Outstanding</span>
                <span className={cx('stat-value', totals.limit > 0 && (totals.limit - totals.available) / totals.limit > 0.3 && 'up')}>
                  {formatINRRound(totals.limit - totals.available)}
                </span>
                <span className="stat-sub">
                  {totals.limit ? `${(((totals.limit - totals.available) / totals.limit) * 100).toFixed(0)}% utilisation` : ''}
                </span>
              </div>
            </section>
          )}

          <div className="card-row">
            {cards.map((c) => (
              <CardVisual key={c.id} card={c} selected={c.id === selected} onClick={() => setSelected(c.id)} />
            ))}
          </div>

          {card && (
            <div className="grid-2">
              <section className="card">
                <div className="card-title-row">
                  <h2 className="card-title">{card.name}{card.archived && <span className="tag">removed</span>}</h2>
                  <button className="link-btn small-text" onClick={() => setEditing(card)}>Edit</button>
                </div>
                <dl className="kv">
                  <dt>Credit limit</dt><dd>{formatINR(card.credit_limit)}</dd>
                  <dt>Available</dt><dd><b>{formatINR(card.available)}</b></dd>
                  <dt>Used</dt>
                  <dd className={cx((card.utilization ?? 0) > 30 && 'text-danger')}>
                    {formatINR(card.used)} {card.utilization != null && <span className="muted">({card.utilization}%)</span>}
                  </dd>
                  <dt>Spent this month</dt><dd>{formatINR(card.month_spent)} <span className="muted">· {card.month_count} txns</span></dd>
                  {card.statement_day && <><dt>Statement</dt><dd>{ordinal(card.statement_day)} · next {nextDay(card.statement_day)}</dd></>}
                  {card.due_day && <><dt>Payment due</dt><dd>{ordinal(card.due_day)} · next {nextDay(card.due_day)}</dd></>}
                </dl>
                {(card.utilization ?? 0) > 30 && (
                  <p className="hint">Keeping utilisation under 30% is generally better for your credit score.</p>
                )}
                <div className="btn-row">
                  {!card.archived && <button className="btn primary" onClick={() => setPaying(card)}>Record payment / refund</button>}
                  <button className="btn ghost" onClick={() => setSyncing(card)}>Update balance</button>
                  {card.archived
                    ? <button className="btn ghost" onClick={() => restore(card)}>Restore</button>
                    : <button className="btn danger-ghost" onClick={() => archive(card)}>Remove</button>}
                </div>
              </section>

              <section className="card">
                <h2 className="card-title">Last 3 months on this card</h2>
                {!txns ? <Spinner /> : txns.length === 0 ? (
                  <p className="muted small-text">No spends yet. Choose “Credit card → {card.name}” when adding an expense.</p>
                ) : (
                  <ul className="tx-list">
                    {txns.slice(0, 25).map((e) => (
                      <li key={e.id}>
                        <button className="tx" onClick={() => setEditingTx(e)}>
                          <CategoryBadge id={e.category} size="sm" />
                          <span className="tx-main">
                            <span className="tx-title">{e.note || cat(e.category).label}</span>
                            <span className="tx-sub">{shortDate(e.date)} · {cat(e.category).label}</span>
                          </span>
                          <span className="tx-amt">−{formatINR(e.amount)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {payments && payments.length > 0 && (
                  <>
                    <h2 className="card-title spaced">Payments & refunds</h2>
                    <ul className="tx-list">
                      {payments.slice(0, 12).map((p) => (
                        <li key={p.id} className="tx static">
                          <span className="cat-badge sm pay-in">{p.kind === 'refund' ? '↩' : '✓'}</span>
                          <span className="tx-main">
                            <span className="tx-title">{p.note || (p.kind === 'refund' ? 'Refund' : 'Bill payment')}</span>
                            <span className="tx-sub">{shortDate(p.date)}</span>
                          </span>
                          <span className="tx-amt text-success">+{formatINR(p.amount)}</span>
                          <button className="icon-btn small" onClick={() => removePayment(p)} aria-label="Remove">✕</button>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>
            </div>
          )}

          <label className="toggle-line muted small-text">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            Show removed cards
          </label>
        </>
      ))}

      {editing && <CardForm card={editing === 'new' ? undefined : editing}
        onClose={(saved) => { setEditing(null); if (saved) { setSelected(saved.id); afterChange() } }} />}
      {paying && <PaymentForm card={paying} onClose={(done) => { setPaying(null); if (done) afterChange() }} />}
      {syncing && <BalanceForm card={syncing} onClose={(done) => { setSyncing(null); if (done) afterChange() }} />}
      {editingTx && <ExpenseForm expense={editingTx} onClose={() => { setEditingTx(null); notifyExpensesChanged() }} />}
    </div>
  )
}

function num(v: string) { return v.replace(/[^\d.]/g, '') }

function CardForm({ card, onClose }: { card?: Card; onClose: (saved?: Card) => void }) {
  const [name, setName] = useState(card?.name ?? '')
  const [bank, setBank] = useState(card?.bank ?? '')
  const [last4, setLast4] = useState(card?.last4 ?? '')
  const [limit, setLimit] = useState(card ? String(card.credit_limit) : '')
  const [available, setAvailable] = useState(card ? String(card.available) : '')
  const [statementDay, setStatementDay] = useState(card?.statement_day ? String(card.statement_day) : '')
  const [dueDay, setDueDay] = useState(card?.due_day ? String(card.due_day) : '')
  const [color, setColor] = useState(card?.color ?? COLORS[0])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const lim = Number(limit)
    const av = available === '' ? lim : Number(available)
    if (!name.trim()) return setError('Give the card a name')
    if (!lim || lim <= 0) return setError('Enter the credit limit')
    if (!Number.isFinite(av)) return setError('Enter the available balance')
    setBusy(true)
    setError(null)
    const body: CardInput = {
      name: name.trim(), bank: bank.trim(), last4, credit_limit: lim, available: av,
      statement_day: statementDay ? Number(statementDay) : null, due_day: dueDay ? Number(dueDay) : null, color,
    }
    try {
      onClose(card ? await api.updateCard(card.id, body) : await api.createCard(body))
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const days = Array.from({ length: 31 }, (_, i) => i + 1)
  return (
    <Modal title={card ? 'Edit card' : 'Add credit card'} onClose={() => onClose()} footer={
      <>
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={() => onClose()} disabled={busy}>Cancel</button>
        <button type="submit" form="card-form" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </>
    }>
      <form id="card-form" className="form" onSubmit={submit}>
        <div className="row-2">
          <label className="field">
            <span className="field-label">Card name</span>
            <input autoFocus value={name} maxLength={40} placeholder="e.g. HDFC Millennia" onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Bank</span>
            <input value={bank} maxLength={40} placeholder="e.g. HDFC Bank" onChange={(e) => setBank(e.target.value)} />
          </label>
        </div>
        <div className="row-3">
          <label className="field">
            <span className="field-label">Credit limit (₹)</span>
            <input inputMode="decimal" value={limit} onChange={(e) => setLimit(num(e.target.value))} />
          </label>
          <label className="field">
            <span className="field-label">Available now (₹)</span>
            <input inputMode="decimal" value={available} placeholder={limit || ''} onChange={(e) => setAvailable(num(e.target.value))} />
          </label>
          <label className="field">
            <span className="field-label">Last 4 digits</span>
            <input inputMode="numeric" value={last4} maxLength={4} placeholder="Optional"
              onChange={(e) => setLast4(e.target.value.replace(/\D/g, ''))} />
          </label>
        </div>
        {card && <p className="hint">Changing “Available now” resets the balance to that figure — handy to match your bank app.</p>}
        <div className="row-2">
          <label className="field">
            <span className="field-label">Statement day</span>
            <select value={statementDay} onChange={(e) => setStatementDay(e.target.value)}>
              <option value="">Not set</option>
              {days.map((d) => <option key={d} value={d}>{ordinal(d)}</option>)}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Payment due day</span>
            <select value={dueDay} onChange={(e) => setDueDay(e.target.value)}>
              <option value="">Not set</option>
              {days.map((d) => <option key={d} value={d}>{ordinal(d)}</option>)}
            </select>
          </label>
        </div>
        <div className="field">
          <span className="field-label">Colour</span>
          <div className="swatches">
            {COLORS.map((c) => (
              <button key={c} type="button" className={cx('swatch', color === c && 'active')} style={{ background: c }}
                onClick={() => setColor(c)} aria-label={c} />
            ))}
          </div>
        </div>
        <p className="hint">Only the last 4 digits are ever stored — never enter the full card number.</p>
        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}

function PaymentForm({ card, onClose }: { card: Card; onClose: (done: boolean) => void }) {
  const [kind, setKind] = useState<'payment' | 'refund'>('payment')
  const [amount, setAmount] = useState(card.used > 0 ? String(card.used) : '')
  const [date, setDate] = useState(todayISO())
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const v = Number(amount)
    if (!v || v <= 0) return setError('Enter an amount')
    setBusy(true)
    try {
      await api.addCardPayment(card.id, { amount: v, date, note, kind })
      onClose(true)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Modal title={`${card.name}: payment or refund`} onClose={() => onClose(false)} footer={
      <>
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={() => onClose(false)}>Cancel</button>
        <button type="submit" form="pay-form" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </>
    }>
      <form id="pay-form" className="form" onSubmit={submit}>
        <div className="seg">
          <button type="button" className={kind === 'payment' ? 'active' : ''} onClick={() => setKind('payment')}>Bill payment</button>
          <button type="button" className={kind === 'refund' ? 'active' : ''} onClick={() => setKind('refund')}>Refund / cashback</button>
        </div>
        <label className="amount-field">
          <span className="amount-prefix">₹</span>
          <input autoFocus inputMode="decimal" value={amount} onChange={(e) => setAmount(num(e.target.value))} />
        </label>
        {kind === 'payment' && card.used > 0 && (
          <div className="chips">
            <button type="button" className="chip" onClick={() => setAmount(String(card.used))}>Full outstanding {formatINRRound(card.used)}</button>
          </div>
        )}
        <div className="row-2">
          <label className="field">
            <span className="field-label">Date</span>
            <input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Note</span>
            <input value={note} maxLength={120} placeholder={kind === 'refund' ? 'e.g. Amazon return' : 'e.g. Oct statement'}
              onChange={(e) => setNote(e.target.value)} />
          </label>
        </div>
        <p className="hint">Adds to the available balance. Not counted as an expense.</p>
        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}

function BalanceForm({ card, onClose }: { card: Card; onClose: (done: boolean) => void }) {
  const [value, setValue] = useState(String(card.available))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(e: FormEvent) {
    e.preventDefault()
    const v = Number(value)
    if (value === '' || !Number.isFinite(v)) return setError('Enter the available balance')
    setBusy(true)
    try { await api.setCardBalance(card.id, v); onClose(true) } catch (err) { setError((err as Error).message); setBusy(false) }
  }
  return (
    <Modal title="Update available balance" onClose={() => onClose(false)} footer={
      <>
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={() => onClose(false)}>Cancel</button>
        <button type="submit" form="bal-form" className="btn primary" disabled={busy}>Update</button>
      </>
    }>
      <form id="bal-form" className="form" onSubmit={submit}>
        <p className="muted small-text">Use this if the app and your bank disagree (interest, fees, a spend you didn't log…).
          Enter what your bank app shows as available.</p>
        <label className="amount-field">
          <span className="amount-prefix">₹</span>
          <input autoFocus inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value.replace(/[^\d.-]/g, ''))} />
        </label>
        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}
