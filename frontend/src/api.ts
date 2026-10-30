import type {
  AuthResponse, Card, CardInput, CardPayment, Category, Expense, ExpenseInput, Insights, Loan,
  LoanInput, LoansResponse, Meta, Recurring, RecurringInput, Summary, User,
} from './types'
import { saveFile } from './native'

const TOKEN_KEY = 'spend-a-thon.token'

export const tokenStore = {
  get(): string | null {
    try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
  },
  set(token: string) {
    try { localStorage.setItem(TOKEN_KEY, token) } catch { /* private mode */ }
  },
  clear() {
    try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
  },
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn
}

function detailMessage(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string }) => (d.msg ?? '').replace(/^Value error, /, ''))
      .filter(Boolean)
      .join('; ')
  }
  return undefined
}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && typeof init.body === 'string') headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(`/api${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, "Couldn't reach the server. Check your connection.")
  }
  if (res.status === 401 && token) {
    tokenStore.clear()
    onUnauthorized?.()
  }
  if (!res.ok) {
    let msg = `Something went wrong (${res.status})`
    try { msg = detailMessage((await res.json()).detail) || msg } catch { /* not json */ }
    throw new ApiError(res.status, msg)
  }
  return res
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await raw(path, init)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) })

export const api = {
  // auth
  register: (b: { name: string; email: string; password: string }) =>
    request<AuthResponse>('/auth/register', json('POST', b)),
  login: (b: { email: string; password: string }) => request<AuthResponse>('/auth/login', json('POST', b)),
  me: () => request<User>('/auth/me'),
  meta: () => request<Meta>('/meta'),

  // expenses
  listExpenses: (f: { month?: string; start?: string; end?: string; category?: string; payment?: string }) => {
    const q = new URLSearchParams()
    Object.entries(f).forEach(([k, v]) => v && q.set(k, v))
    return request<Expense[]>(`/expenses?${q}`)
  },
  createExpense: (b: ExpenseInput) => request<Expense>('/expenses', json('POST', b)),
  updateExpense: (id: string, b: ExpenseInput) => request<Expense>(`/expenses/${id}`, json('PUT', b)),
  deleteExpense: (id: string) => request<void>(`/expenses/${id}`, { method: 'DELETE' }),

  // budgets
  getBudgets: () => request<{ budgets: Record<string, number> }>('/budgets'),
  saveBudgets: (budgets: Record<string, number | null>) =>
    request<{ budgets: Record<string, number> }>('/budgets', json('PUT', { budgets })),

  // recurring
  listRecurring: () => request<Recurring[]>('/recurring'),
  createRecurring: (b: RecurringInput) => request<Recurring>('/recurring', json('POST', b)),
  updateRecurring: (id: string, b: RecurringInput) => request<Recurring>(`/recurring/${id}`, json('PUT', b)),
  deleteRecurring: (id: string) => request<void>(`/recurring/${id}`, { method: 'DELETE' }),

  // categories
  createCategory: (b: { label: string; emoji: string; color?: string | null }) =>
    request<Category>('/categories', json('POST', b)),
  updateCategory: (id: string, b: { label: string; emoji: string; color?: string | null }) =>
    request<Category>(`/categories/${id}`, json('PUT', b)),
  deleteCategory: (id: string) => request<void>(`/categories/${id}`, { method: 'DELETE' }),

  // credit cards
  listCards: (includeArchived = false) => request<Card[]>(`/cards${includeArchived ? '?include_archived=true' : ''}`),
  createCard: (b: CardInput) => request<Card>('/cards', json('POST', b)),
  updateCard: (id: string, b: CardInput) => request<Card>(`/cards/${id}`, json('PUT', b)),
  archiveCard: (id: string) => request<void>(`/cards/${id}`, { method: 'DELETE' }),
  restoreCard: (id: string) => request<Card>(`/cards/${id}/restore`, { method: 'POST' }),
  setCardBalance: (id: string, available: number) => request<Card>(`/cards/${id}/balance`, json('PUT', { available })),
  cardPayments: (id: string) => request<CardPayment[]>(`/cards/${id}/payments`),
  addCardPayment: (id: string, b: { amount: number; date: string; note: string; kind: 'payment' | 'refund' }) =>
    request<{ payment: CardPayment; card: Card }>(`/cards/${id}/payments`, json('POST', b)),
  deleteCardPayment: (id: string, pid: string) => request<Card>(`/cards/${id}/payments/${pid}`, { method: 'DELETE' }),

  // loans & borrowings
  listLoans: () => request<LoansResponse>('/loans'),
  createLoan: (b: LoanInput) => request<Loan>('/loans', json('POST', b)),
  updateLoan: (id: string, b: LoanInput) => request<Loan>(`/loans/${id}`, json('PUT', b)),
  deleteLoan: (id: string) => request<void>(`/loans/${id}`, { method: 'DELETE' }),
  addRepayment: (id: string, b: { amount: number; date: string; note: string }) =>
    request<Loan>(`/loans/${id}/repayments`, json('POST', b)),
  deleteRepayment: (id: string, rid: string) => request<Loan>(`/loans/${id}/repayments/${rid}`, { method: 'DELETE' }),

  // insights
  summary: (month: string) => request<Summary>(`/summary?month=${month}`),
  insights: (start: string, end: string) => request<Insights>(`/insights?${new URLSearchParams({ start, end })}`),
  async exportCsv(start: string, end: string) {
    const res = await raw(`/export?${new URLSearchParams({ start, end })}`)
    const cd = res.headers.get('Content-Disposition') ?? ''
    const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? `expenses_${start}_to_${end}.csv`
    await saveFile(await res.blob(), name)
  },
}

/** Tell any open page that expenses changed (e.g. after a quick-add from the floating button). */
export const EXPENSES_CHANGED = 'spend-a-thon:expenses-changed'
export function notifyExpensesChanged() {
  window.dispatchEvent(new Event(EXPENSES_CHANGED))
}

const LAST_PAYMENT_KEY = 'spend-a-thon.last-payment'
export const lastPayment = {
  get(): { payment_method: string | null; card_id: string | null } {
    try {
      const v = JSON.parse(localStorage.getItem(LAST_PAYMENT_KEY) ?? 'null')
      if (v && typeof v === 'object') return { payment_method: v.payment_method ?? null, card_id: v.card_id ?? null }
    } catch { /* ignore */ }
    return { payment_method: 'Google Pay', card_id: null }
  },
  set(v: { payment_method: string | null; card_id: string | null }) {
    try { localStorage.setItem(LAST_PAYMENT_KEY, JSON.stringify(v)) } catch { /* ignore */ }
  },
}
