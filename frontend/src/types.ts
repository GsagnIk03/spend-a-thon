export interface User {
  id: string
  name: string
  email: string
}

export interface AuthResponse {
  token: string
  user: User
}

export interface Category {
  id: string
  label: string
  emoji: string
  color: string
  custom?: boolean
}

export interface Card {
  id: string
  name: string
  bank: string
  last4: string
  credit_limit: number
  available: number
  used: number
  utilization: number | null
  statement_day: number | null
  due_day: number | null
  color: string | null
  archived: boolean
  month_spent: number
  month_count: number
}

export interface CardInput {
  name: string
  bank: string
  last4: string
  credit_limit: number
  available: number
  statement_day: number | null
  due_day: number | null
  color: string | null
}

export interface CardPayment {
  id: string
  card_id: string
  amount: number
  date: string
  note: string
  kind: 'payment' | 'refund'
}

export interface Meta {
  categories: Category[]
  payment_methods: string[]
  cards: Card[]
}

export interface Payment {
  payment_method: string | null
  card_id: string | null
}

export interface Expense extends Payment {
  id: string
  amount: number
  date: string
  category: string
  note: string
  has_receipt: boolean
  recurring_id: string | null
  loan_id: string | null
  created_at: string | null
}

export interface ExpenseInput extends Payment {
  amount: number
  date: string
  category: string
  note: string
}

export interface Recurring extends Payment {
  id: string
  amount: number
  category: string
  note: string
  day_of_month: number
  start_month: string
  end_month: string | null
  active: boolean
  last_generated_month: string | null
  next_due: string | null
}

export type RecurringInput = Omit<Recurring, 'id' | 'last_generated_month' | 'next_due'>

export interface PaymentRow {
  key: string
  method: string
  card_id: string | null
  label: string
  color: string | null
  total: number
  count: number
  share?: number
  monthly?: { month: string; total: number }[]
}

export interface Summary {
  month: string
  total: number
  count: number
  previous_total: number
  budget_total: number | null
  by_category: { category: string; spent: number; count: number; budget: number | null }[]
  by_payment: PaymentRow[]
  by_day: { date: string; total: number }[]
  trend: { month: string; total: number }[]
  top: Expense[]
}

export interface Insights {
  start: string
  end: string
  months: number
  total: number
  count: number
  monthly_average: number
  monthly: { month: string; total: number }[]
  by_category: {
    category: string
    total: number
    count: number
    average: number
    share: number
    monthly: { month: string; total: number }[]
  }[]
  by_payment: PaymentRow[]
  by_method: { method: string; total: number; count: number }[]
}

export interface Repayment {
  id: string
  amount: number
  date: string
  note: string
}

export interface Loan extends Payment {
  id: string
  kind: 'loan' | 'borrowing'
  lender: string
  taken_by: string
  principal: number
  note: string
  taken_on: string | null
  repayments: Repayment[]
  interest_rate: number | null
  total_interest: number | null
  installment: number | null
  emi_day: number | null
  emi_count: number | null
  first_emi_date: string | null
  emi_adjustment: number
  insurance: boolean
  log_emis_as_expenses: boolean
  emis_paid: number | null
  emis_due: number | null
  next_emi_date: string | null
  closure_date: string | null
  total_payable: number
  total_paid: number
  remaining: number
  monthly_outgo: number
  status: 'active' | 'closed'
}

export interface LoanInput extends Payment {
  kind: 'loan' | 'borrowing'
  lender: string
  taken_by: string
  principal: number
  note: string
  taken_on: string | null
  interest_rate: number | null
  total_interest: number | null
  installment: number | null
  emi_day: number | null
  emi_count: number | null
  first_emi_date: string | null
  emi_adjustment: number
  insurance: boolean
  log_emis_as_expenses: boolean
}

export interface LoansResponse {
  loans: Loan[]
  summary: {
    outstanding: number
    monthly_emi: number
    total_borrowed: number
    total_paid: number
    active_count: number
    outstanding_loans: number
    outstanding_borrowings: number
  }
}
