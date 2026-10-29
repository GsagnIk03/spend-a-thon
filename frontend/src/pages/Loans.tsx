import { Fragment, useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, notifyExpensesChanged } from '../api'
import { Empty, ErrorNote, Modal, PaymentPicker, ProgressBar, Spinner } from '../components/ui'
import { useMeta } from '../hooks'
import type { Loan, LoanInput, LoansResponse, Payment } from '../types'
import { cx, formatINR, formatINRRound, ordinal, todayISO } from '../utils'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function fmtDate(d: string | null) {
  if (!d) return '—'
  const [y, m, day] = d.split('-').map(Number)
  return `${day} ${MONTHS[m - 1]} ${String(y).slice(2)}`
}
const paidPct = (l: Loan) => (l.total_payable ? Math.min(100, (l.total_paid / l.total_payable) * 100) : 0)

export default function Loans() {
  const [data, setData] = useState<LoansResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<{ kind: 'loan' | 'borrowing'; loan?: Loan } | null>(null)
  const [detail, setDetail] = useState<Loan | null>(null)
  const [showClosed, setShowClosed] = useState(false)

  const load = useCallback(() => {
    api.listLoans().then((d) => {
      setData(d)
      setDetail((cur) => (cur ? d.loans.find((l) => l.id === cur.id) ?? null : null))
    }).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const loans = data?.loans ?? []
  const visible = loans.filter((l) => showClosed || l.status === 'active')
  const emi = visible.filter((l) => l.kind === 'loan')
  const borrowings = visible.filter((l) => l.kind === 'borrowing')
  const closedCount = loans.filter((l) => l.status === 'closed').length
  const s = data?.summary

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Loans & borrowings</h1>
          <p className="muted">EMIs paid, dues and balances update themselves from each loan's schedule.</p>
        </div>
        <div className="btn-row">
          <button className="btn ghost" onClick={() => setForm({ kind: 'borrowing' })}>+ Borrowing</button>
          <button className="btn primary" onClick={() => setForm({ kind: 'loan' })}>+ EMI loan</button>
        </div>
      </div>
      <ErrorNote message={error} />
      {!data && !error && <Spinner />}

      {data && s && (loans.length === 0 ? (
        <div className="card">
          <Empty icon="🏦" title="No loans or borrowings">
            Add bank/NBFC loans with EMIs, or money you've borrowed from friends and family.
          </Empty>
        </div>
      ) : (
        <>
          <section className="stats">
            <div className="stat hero">
              <span className="stat-label">Total outstanding</span>
              <span className="stat-value">{formatINRRound(s.outstanding)}</span>
              <span className="stat-sub">{s.active_count} active</span>
            </div>
            <div className="stat">
              <span className="stat-label">EMIs every month</span>
              <span className="stat-value">{formatINRRound(s.monthly_emi)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Bank & NBFC loans</span>
              <span className="stat-value">{formatINRRound(s.outstanding_loans)}</span>
              <span className="stat-sub">incl. interest</span>
            </div>
            <div className="stat">
              <span className="stat-label">Owed to people</span>
              <span className="stat-value">{formatINRRound(s.outstanding_borrowings)}</span>
            </div>
          </section>

          {emi.length > 0 && (
            <section className="card flush">
              <h2 className="card-title pad">EMI loans</h2>
              <div className="table-wrap desktop-only">
                <table className="loan-table">
                  <thead>
                    <tr>
                      <th>Creditor</th><th>Taken by</th><th className="num">Amount</th><th className="num">Rate</th>
                      <th className="num">Interest</th><th className="num">EMI</th><th>EMI date</th>
                      <th className="num">EMIs paid</th><th className="num">Paid</th><th className="num">Remaining</th>
                      <th>Next EMI</th><th>Closes</th><th>Ins.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {emi.map((l) => (
                      <tr key={l.id} onClick={() => setDetail(l)} className={cx(l.status === 'closed' && 'closed')}>
                        <td><b>{l.lender}</b></td>
                        <td>{l.taken_by || '—'}</td>
                        <td className="num">{formatINRRound(l.principal)}</td>
                        <td className="num">{l.interest_rate != null ? `${l.interest_rate}%` : '—'}</td>
                        <td className="num">{formatINRRound(l.total_interest ?? 0)}</td>
                        <td className="num">{formatINRRound(l.installment ?? 0)}</td>
                        <td>{ordinal(l.emi_day ?? 0)}</td>
                        <td className="num">
                          {l.emis_paid}/{l.emi_count}
                          <div className="mini-progress"><span style={{ width: `${paidPct(l)}%` }} /></div>
                        </td>
                        <td className="num">{formatINRRound(l.total_paid)}</td>
                        <td className="num"><b>{formatINRRound(l.remaining)}</b></td>
                        <td>{l.next_emi_date ? fmtDate(l.next_emi_date) : <span className="tag">done</span>}</td>
                        <td>{fmtDate(l.closure_date)}</td>
                        <td>{l.insurance ? '✓' : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="loan-cards mobile-only">
                {emi.map((l) => <LoanCard key={l.id} loan={l} onOpen={() => setDetail(l)} />)}
              </ul>
            </section>
          )}

          {borrowings.length > 0 && (
            <section className="card flush">
              <h2 className="card-title pad">Borrowed from people</h2>
              <ul className="loan-cards">
                {borrowings.map((l) => <LoanCard key={l.id} loan={l} onOpen={() => setDetail(l)} />)}
              </ul>
            </section>
          )}

          {closedCount > 0 && (
            <label className="toggle-line muted small-text">
              <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
              Show {closedCount} closed
            </label>
          )}
        </>
      ))}

      {form && (
        <LoanForm kind={form.kind} loan={form.loan}
          onClose={(saved) => { setForm(null); if (saved) { load(); notifyExpensesChanged() } }} />
      )}
      {detail && (
        <LoanDetail loan={detail} onClose={() => setDetail(null)} onChanged={load}
          onEdit={() => { setForm({ kind: detail.kind, loan: detail }); setDetail(null) }} />
      )}
    </div>
  )
}

function LoanCard({ loan: l, onOpen }: { loan: Loan; onOpen: () => void }) {
  return (
    <li>
      <button className={cx('loan-card', l.status === 'closed' && 'closed')} onClick={onOpen}>
        <div className="loan-card-top">
          <div>
            <b>{l.lender}</b>
            <div className="muted small-text">
              {l.kind === 'loan'
                ? `${formatINRRound(l.installment ?? 0)}/mo on the ${ordinal(l.emi_day ?? 0)} · ${l.emis_paid}/${l.emi_count} EMIs`
                : `${l.taken_by ? `Taken by ${l.taken_by} · ` : ''}${l.repayments.length} repayment${l.repayments.length === 1 ? '' : 's'}`}
            </div>
          </div>
          <div className="loan-card-amt">
            <b>{formatINRRound(l.remaining)}</b>
            <span className="muted small-text">of {formatINRRound(l.total_payable)}</span>
          </div>
        </div>
        <ProgressBar value={l.total_paid} max={l.total_payable} />
        {l.kind === 'loan' && l.next_emi_date && <div className="muted small-text">Next EMI {fmtDate(l.next_emi_date)} · closes {fmtDate(l.closure_date)}</div>}
        {l.status === 'closed' && <div className="small-text text-success">✓ Fully repaid</div>}
      </button>
    </li>
  )
}

function LoanDetail({ loan: l, onClose, onChanged, onEdit }: {
  loan: Loan; onClose: () => void; onChanged: () => void; onEdit: () => void
}) {
  const { paymentLabel } = useMeta()
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(todayISO())
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function addRepayment(e: FormEvent) {
    e.preventDefault()
    const v = Number(amount)
    if (!v || v <= 0) return setError('Enter an amount')
    setBusy(true)
    setError(null)
    try {
      await api.addRepayment(l.id, { amount: v, date, note })
      setAmount('')
      setNote('')
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function removeRepayment(rid: string) {
    if (!confirm('Remove this repayment?')) return
    try { await api.deleteRepayment(l.id, rid); onChanged() } catch (err) { setError((err as Error).message) }
  }

  async function remove() {
    if (!confirm(`Delete ${l.lender}? This can't be undone. (EMIs already logged as expenses stay.)`)) return
    try { await api.deleteLoan(l.id); onChanged(); onClose() } catch (err) { setError((err as Error).message) }
  }

  const rows: [string, string][] = l.kind === 'loan' ? [
    ['Taken by', l.taken_by || '—'],
    ['Principal', formatINR(l.principal)],
    ['Interest rate', l.interest_rate != null ? `${l.interest_rate}% p.a.` : '—'],
    ['Total interest', formatINR(l.total_interest ?? 0)],
    ['Total payable', formatINR(l.total_payable)],
    ['EMI', `${formatINR(l.installment ?? 0)} on the ${ordinal(l.emi_day ?? 0)}`],
    ['EMIs', `${l.emis_paid} paid · ${l.emis_due} due · ${l.emi_count} total`],
    ['First EMI', fmtDate(l.first_emi_date)],
    ['Next EMI', fmtDate(l.next_emi_date)],
    ['Closes', fmtDate(l.closure_date)],
    ['Insurance', l.insurance ? 'Yes' : 'No'],
    ['Logged as expenses', l.log_emis_as_expenses ? `Yes${paymentLabel(l) ? ` · ${paymentLabel(l)}` : ''}` : 'No'],
  ] : [
    ['Taken by', l.taken_by || '—'],
    ['Amount', formatINR(l.principal)],
    ['Taken on', fmtDate(l.taken_on)],
  ]

  return (
    <Modal title={l.lender} onClose={onClose} footer={
      <>
        <button className="btn danger-ghost" onClick={remove}>Delete</button>
        <span className="spacer" />
        <button className="btn ghost" onClick={onEdit}>Edit</button>
        <button className="btn primary" onClick={onClose}>Done</button>
      </>
    }>
      <div className="form">
        <div className="loan-hero">
          <div>
            <span className="muted small-text">Remaining</span>
            <b className="big-num">{formatINR(l.remaining)}</b>
          </div>
          <div className="right">
            <span className="muted small-text">Paid so far</span>
            <b>{formatINR(l.total_paid)}</b>
          </div>
        </div>
        <ProgressBar value={l.total_paid} max={l.total_payable} />
        <dl className="kv">
          {rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
        </dl>
        {l.note && <p className="info-note">{l.note}</p>}

        <div>
          <h3 className="section-label">{l.kind === 'loan' ? 'Prepayments / extra payments' : 'Repayments'}</h3>
          {l.repayments.length === 0 && <p className="muted small-text">None yet.</p>}
          <ul className="tx-list">
            {l.repayments.map((r) => (
              <li key={r.id} className="tx static">
                <span className="tx-main">
                  <span className="tx-title">{formatINR(r.amount)}</span>
                  <span className="tx-sub">{fmtDate(r.date)}{r.note && ` · ${r.note}`}</span>
                </span>
                <button className="icon-btn small" onClick={() => removeRepayment(r.id)} aria-label="Remove">✕</button>
              </li>
            ))}
          </ul>
          {l.status === 'active' && (
            <form className="repay-form" onSubmit={addRepayment}>
              <input inputMode="decimal" placeholder="Amount ₹" value={amount}
                onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
              <input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} />
              <input placeholder="Note (optional)" value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} />
              <button className="btn primary" disabled={busy}>{l.kind === 'loan' ? 'Add prepayment' : 'Add repayment'}</button>
            </form>
          )}
          {l.kind === 'loan' && <p className="hint">Regular EMIs are counted automatically — only record extra payments here.</p>}
        </div>
        <ErrorNote message={error} />
      </div>
    </Modal>
  )
}

function LoanForm({ kind: initialKind, loan, onClose }: {
  kind: 'loan' | 'borrowing'; loan?: Loan; onClose: (saved?: Loan) => void
}) {
  const [kind, setKind] = useState(loan?.kind ?? initialKind)
  const [lender, setLender] = useState(loan?.lender ?? '')
  const [takenBy, setTakenBy] = useState(loan?.taken_by ?? '')
  const [principal, setPrincipal] = useState(loan ? String(loan.principal) : '')
  const [note, setNote] = useState(loan?.note ?? '')
  const [takenOn, setTakenOn] = useState(loan?.taken_on ?? '')
  const [rate, setRate] = useState(loan?.interest_rate != null ? String(loan.interest_rate) : '')
  const [installment, setInstallment] = useState(loan?.installment != null ? String(loan.installment) : '')
  const [count, setCount] = useState(loan?.emi_count != null ? String(loan.emi_count) : '')
  const [firstDate, setFirstDate] = useState(loan?.first_emi_date ?? '')
  const [emiDay, setEmiDay] = useState(loan?.emi_day != null ? String(loan.emi_day) : '')
  const [interest, setInterest] = useState(loan?.total_interest != null ? String(loan.total_interest) : '')
  const [insurance, setInsurance] = useState(loan?.insurance ?? false)
  const [adjustment, setAdjustment] = useState(String(loan?.emi_adjustment ?? 0))
  const [logEmis, setLogEmis] = useState(loan?.log_emis_as_expenses ?? false)
  const [payment, setPayment] = useState<Payment>({
    payment_method: loan?.payment_method ?? 'Net banking', card_id: loan?.card_id ?? null,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const numOrNull = (v: string) => (v.trim() === '' ? null : Number(v))
  const estInterest = Number(installment) * Number(count) - Number(principal)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!lender.trim()) return setError(kind === 'loan' ? 'Enter the bank / lender' : 'Who did you borrow from?')
    if (!Number(principal)) return setError('Enter the amount')
    if (kind === 'loan' && (!Number(installment) || !Number(count) || !firstDate)) {
      return setError('EMI amount, number of EMIs and first EMI date are needed')
    }
    setBusy(true)
    setError(null)
    const body: LoanInput = {
      kind, lender: lender.trim(), taken_by: takenBy.trim(), principal: Number(principal), note,
      taken_on: kind === 'borrowing' && takenOn ? takenOn : null,
      interest_rate: kind === 'loan' ? numOrNull(rate) : null,
      total_interest: kind === 'loan' ? numOrNull(interest) : null,
      installment: kind === 'loan' ? Number(installment) : null,
      emi_count: kind === 'loan' ? Number(count) : null,
      first_emi_date: kind === 'loan' ? firstDate : null,
      emi_day: kind === 'loan' ? numOrNull(emiDay) : null,
      emi_adjustment: kind === 'loan' ? Number(adjustment) || 0 : 0,
      insurance: kind === 'loan' && insurance,
      log_emis_as_expenses: kind === 'loan' && logEmis,
      ...(kind === 'loan' && logEmis ? payment : { payment_method: null, card_id: null }),
    }
    try {
      onClose(loan ? await api.updateLoan(loan.id, body) : await api.createLoan(body))
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const days = Array.from({ length: 31 }, (_, i) => i + 1)
  return (
    <Modal title={loan ? `Edit ${loan.lender}` : kind === 'loan' ? 'New EMI loan' : 'New borrowing'} onClose={() => onClose()} footer={
      <>
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={() => onClose()} disabled={busy}>Cancel</button>
        <button type="submit" form="loan-form" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </>
    }>
      <form id="loan-form" className="form" onSubmit={submit}>
        {!loan && (
          <div className="seg">
            <button type="button" className={kind === 'loan' ? 'active' : ''} onClick={() => setKind('loan')}>EMI loan</button>
            <button type="button" className={kind === 'borrowing' ? 'active' : ''} onClick={() => setKind('borrowing')}>From a person</button>
          </div>
        )}
        <div className="row-2">
          <label className="field">
            <span className="field-label">{kind === 'loan' ? 'Bank / lender' : 'Borrowed from'}</span>
            <input autoFocus value={lender} maxLength={60} placeholder={kind === 'loan' ? 'e.g. IndusInd Bank' : 'Name'}
              onChange={(e) => setLender(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Taken by</span>
            <input value={takenBy} maxLength={60} placeholder="In whose name" onChange={(e) => setTakenBy(e.target.value)} />
          </label>
        </div>
        <div className="row-2">
          <label className="field">
            <span className="field-label">{kind === 'loan' ? 'Loan amount (₹)' : 'Amount (₹)'}</span>
            <input inputMode="decimal" value={principal} onChange={(e) => setPrincipal(e.target.value.replace(/[^\d.]/g, ''))} />
          </label>
          {kind === 'loan' ? (
            <label className="field">
              <span className="field-label">Interest rate (% p.a.)</span>
              <input inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value.replace(/[^\d.]/g, ''))} />
            </label>
          ) : (
            <label className="field">
              <span className="field-label">Taken on <span className="muted">(optional)</span></span>
              <input type="date" value={takenOn} max={todayISO()} onChange={(e) => setTakenOn(e.target.value)} />
            </label>
          )}
        </div>

        {kind === 'loan' && (
          <>
            <div className="row-3">
              <label className="field">
                <span className="field-label">EMI (₹/month)</span>
                <input inputMode="decimal" value={installment} onChange={(e) => setInstallment(e.target.value.replace(/[^\d.]/g, ''))} />
              </label>
              <label className="field">
                <span className="field-label">Number of EMIs</span>
                <input inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value.replace(/\D/g, ''))} />
              </label>
              <label className="field">
                <span className="field-label">First EMI date</span>
                <input type="date" value={firstDate} onChange={(e) => setFirstDate(e.target.value)} />
              </label>
            </div>
            <div className="row-3">
              <label className="field">
                <span className="field-label">EMI day after that</span>
                <select value={emiDay} onChange={(e) => setEmiDay(e.target.value)}>
                  <option value="">Same as first EMI</option>
                  {days.map((d) => <option key={d} value={d}>{ordinal(d)} of every month</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field-label">Total interest (₹)</span>
                <input inputMode="decimal" value={interest} placeholder={estInterest > 0 ? `≈ ${Math.round(estInterest)}` : 'From your schedule'}
                  onChange={(e) => setInterest(e.target.value.replace(/[^\d.]/g, ''))} />
              </label>
              <label className="field">
                <span className="field-label">Missed/extra EMIs</span>
                <input inputMode="numeric" value={adjustment} onChange={(e) => setAdjustment(e.target.value.replace(/[^\d-]/g, ''))} />
              </label>
            </div>
            <p className="hint">EMIs paid are counted from the schedule. Use “missed/extra” only if reality differs (e.g. −1 for a bounced EMI).
              Leave total interest blank to use EMI × count − amount.</p>
            <label className="toggle-line">
              <input type="checkbox" checked={insurance} onChange={(e) => setInsurance(e.target.checked)} /> Loan insurance taken
            </label>
            <label className="toggle-line">
              <input type="checkbox" checked={logEmis} onChange={(e) => setLogEmis(e.target.checked)} />
              Add each EMI to my expenses on its date
            </label>
            {logEmis && (
              <div className="field">
                <span className="field-label">EMIs are paid with</span>
                <PaymentPicker value={payment} onChange={setPayment} />
                <span className="hint">Starts from today — past EMIs aren't back-filled. Skip this if you already have a Recurring entry for it.</span>
              </div>
            )}
          </>
        )}

        <label className="field">
          <span className="field-label">Note <span className="muted">(optional)</span></span>
          <input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
        </label>
        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}
