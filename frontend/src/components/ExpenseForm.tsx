import { useState, type FormEvent } from 'react'
import { api, lastPayment, notifyExpensesChanged } from '../api'
import type { Expense, Payment } from '../types'
import { todayISO } from '../utils'
import { CategoryPicker, ErrorNote, Modal, PaymentPicker } from './ui'


export default function ExpenseForm({ expense, onClose }: { expense?: Expense; onClose: () => void }) {
  const [amount, setAmount] = useState(expense ? String(expense.amount) : '')
  const [category, setCategory] = useState(expense?.category ?? 'food')
  const [date, setDate] = useState(expense?.date ?? todayISO())
  const [note, setNote] = useState(expense?.note ?? '')
  const [payment, setPayment] = useState<Payment>(() => expense
    ? { payment_method: expense.payment_method, card_id: expense.card_id }
    : lastPayment.get())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const editing = Boolean(expense)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const value = Number(amount)
    if (!amount || !Number.isFinite(value) || value <= 0) return setError('Enter an amount greater than zero')
    if (Math.round(value * 100) / 100 !== value) return setError('Use at most 2 decimal places')
    setBusy(true)
    setError(null)
    try {
      const body = { amount: value, date, category, note, ...payment }
      if (expense) await api.updateExpense(expense.id, body)
      else await api.createExpense(body)
      if (!expense) lastPayment.set(payment)
      notifyExpensesChanged()
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  async function remove() {
    if (!expense || !confirm('Delete this expense?')) return
    setBusy(true)
    try {
      await api.deleteExpense(expense.id)
      notifyExpensesChanged()
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Modal
      title={editing ? 'Edit expense' : 'Add expense'}
      onClose={onClose}
      footer={
        <>
          {editing && <button type="button" className="btn danger-ghost" onClick={remove} disabled={busy}>Delete</button>}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" form="expense-form" className="btn primary" disabled={busy}>
            {busy ? 'Saving…' : editing ? 'Save' : 'Add expense'}
          </button>
        </>
      }
    >
      <form id="expense-form" onSubmit={submit} className="form">
        {(expense?.recurring_id || expense?.loan_id) && (
          <div className="info-note">
            {expense.loan_id ? '🏦 Added automatically as a loan EMI.' : '🔁 Added automatically from a recurring expense.'}
            {' '}Changes here only affect this entry.
          </div>
        )}
        <label className="amount-field">
          <span className="sr-only">Amount</span>
          <span className="amount-prefix">₹</span>
          <input autoFocus={!editing} inputMode="decimal" placeholder="0" value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
        </label>

        <div className="field">
          <span className="field-label">Category</span>
          <CategoryPicker value={category} onChange={setCategory} />
        </div>

        <div className="row-2">
          <label className="field">
            <span className="field-label">Date</span>
            <input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="field">
            <span className="field-label">Note</span>
            <input value={note} maxLength={200} placeholder="What was it for?" onChange={(e) => setNote(e.target.value)} />
          </label>
        </div>

        <div className="field">
          <span className="field-label">Paid with</span>
          <PaymentPicker value={payment} onChange={setPayment} />
        </div>

        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}
