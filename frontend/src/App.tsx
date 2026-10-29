import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api, setUnauthorizedHandler, tokenStore } from './api'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import { AuthContext, MetaProvider } from './hooks'
import AuthPage from './pages/AuthPage'
import Budgets from './pages/Budgets'
import Cards from './pages/Cards'
import Dashboard from './pages/Dashboard'
import Expenses from './pages/Expenses'
import Insights from './pages/Insights'
import Loans from './pages/Loans'
import More from './pages/More'
import Recurring from './pages/Recurring'
import type { User } from './types'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(() => Boolean(tokenStore.get()))

  const signOut = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const signIn = useCallback((token: string, u: User) => {
    tokenStore.set(token)
    setUser(u)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    if (tokenStore.get()) {
      api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setChecking(false))
    }
    return () => setUnauthorizedHandler(null)
  }, [])

  const auth = useMemo(() => ({ user, signIn, signOut }), [user, signIn, signOut])

  if (checking) return <div className="splash"><Spinner /></div>

  return (
    <AuthContext.Provider value={auth}>
      {!user ? (
        <AuthPage />
      ) : (
        <MetaProvider key={user.id}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="expenses" element={<Expenses />} />
              <Route path="insights" element={<Insights />} />
              <Route path="budgets" element={<Budgets />} />
              <Route path="recurring" element={<Recurring />} />
              <Route path="cards" element={<Cards />} />
              <Route path="loans" element={<Loans />} />
              <Route path="more" element={<More />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </MetaProvider>
      )}
    </AuthContext.Provider>
  )
}
