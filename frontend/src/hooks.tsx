import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, EXPENSES_CHANGED } from './api'
import type { Card, Category, Meta, Payment, User } from './types'

// ---------- auth ----------
export interface AuthState {
  user: User | null
  signIn: (token: string, user: User) => void
  signOut: () => void
}
export const AuthContext = createContext<AuthState>({ user: null, signIn: () => {}, signOut: () => {} })
export const useAuth = () => useContext(AuthContext)

// ---------- categories, payment methods, cards ----------
const FALLBACK_CAT: Category = { id: 'other', label: 'Other', emoji: '📦', color: '#94a3b8' }

interface MetaState {
  meta: Meta | null
  reload: () => Promise<void>
}
const MetaContext = createContext<MetaState>({ meta: null, reload: async () => {} })

export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const reload = useCallback(async () => {
    try { setMeta(await api.meta()) } catch { /* keep previous */ }
  }, [])
  useEffect(() => { reload() }, [reload])
  // card balances change whenever expenses do
  useExpensesChanged(reload)
  const value = useMemo(() => ({ meta, reload }), [meta, reload])
  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>
}

export function useMeta() {
  const { meta, reload } = useContext(MetaContext)
  return useMemo(() => {
    const cats = new Map<string, Category>()
    meta?.categories.forEach((c) => cats.set(c.id, c))
    const cards = new Map<string, Card>()
    meta?.cards.forEach((c) => cards.set(c.id, c))
    const cat = (id: string) => cats.get(id) ?? { ...FALLBACK_CAT, id, label: id.startsWith('c_') ? 'Deleted category' : id }
    const card = (id: string | null | undefined) => (id ? cards.get(id) : undefined)
    return {
      meta,
      reload,
      categories: meta?.categories ?? [],
      paymentMethods: meta?.payment_methods ?? [],
      cards: meta?.cards ?? [],
      activeCards: (meta?.cards ?? []).filter((c) => !c.archived),
      cat,
      card,
      /** "Cash", "Google Pay", "HDFC Millennia ••4417" … */
      paymentLabel: (p: Payment) => {
        if (!p.payment_method) return ''
        if (p.payment_method === 'Credit card' && p.card_id) {
          const c = cards.get(p.card_id)
          return c ? c.name : 'Credit card'
        }
        return p.payment_method
      },
    }
  }, [meta, reload])
}

// ---------- re-run a loader whenever expenses change anywhere ----------
export function useExpensesChanged(cb: () => void) {
  useEffect(() => {
    window.addEventListener(EXPENSES_CHANGED, cb)
    return () => window.removeEventListener(EXPENSES_CHANGED, cb)
  }, [cb])
}

export const PAYMENT_ICONS: Record<string, string> = {
  Cash: '💵',
  'Google Pay': '🟢',
  PhonePe: '🟣',
  Paytm: '🔵',
  'Other UPI': '📲',
  'Credit card': '💳',
  'Debit card': '🏧',
  'Net banking': '🏦',
  Wallet: '👛',
  Other: '•',
  'Not set': '❔',
}
