import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks'
import { cx } from '../utils'
import ExpenseForm from './ExpenseForm'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '📊', end: true },
  { to: '/expenses', label: 'Expenses', icon: '🧾' },
  { to: '/insights', label: 'Insights', icon: '🔍' },
  { to: '/budgets', label: 'Budgets', icon: '🎯' },
  { to: '/recurring', label: 'Recurring', icon: '🔁' },
  { to: '/cards', label: 'Cards', icon: '💳' },
  { to: '/loans', label: 'Loans', icon: '🏦' },
]

// Mobile bottom bar: the four most used + "More"
const TABS = [NAV[0], NAV[1], NAV[2], NAV[5]]
const MORE_PATHS = ['/more', '/budgets', '/recurring', '/loans']

export default function Layout() {
  const { user, signOut } = useAuth()
  const { pathname } = useLocation()
  const [adding, setAdding] = useState(false)
  const initials = (user?.name ?? '?').split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">₹</span> spend-a-thon</div>
        <nav className="topnav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="user-menu">
          <span className="avatar" title={user?.email}>{initials}</span>
          <span className="user-name">{user?.name}</span>
          <button className="btn ghost small logout" onClick={signOut}>Log out</button>
        </div>
      </header>

      <main className="content">
        <Outlet />
      </main>

      <button className="fab" onClick={() => setAdding(true)} aria-label="Add expense">
        <span>+</span><span className="fab-label">Add expense</span>
      </button>

      <nav className="tabbar">
        {TABS.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
            <span className="tab-icon">{n.icon}</span>
            <span>{n.label === 'Dashboard' ? 'Home' : n.label}</span>
          </NavLink>
        ))}
        <NavLink to="/more" className={cx(MORE_PATHS.includes(pathname) && 'active')}>
          <span className="tab-icon">☰</span>
          <span>More</span>
        </NavLink>
      </nav>

      {adding && <ExpenseForm onClose={() => setAdding(false)} />}
    </div>
  )
}
