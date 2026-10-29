import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CategoryManager } from '../components/CategoryEditor'
import { useAuth } from '../hooks'

/** Mobile-only hub for the sections that don't fit in the bottom bar. */
export default function More() {
  const { user, signOut } = useAuth()
  const [cats, setCats] = useState(false)
  return (
    <div className="page">
      <div className="page-head"><h1>More</h1></div>
      <div className="card flush">
        <ul className="more-list">
          <li><Link to="/loans"><span>🏦</span><b>Loans & borrowings</b><span className="chev">›</span></Link></li>
          <li><Link to="/budgets"><span>🎯</span><b>Budgets</b><span className="chev">›</span></Link></li>
          <li><Link to="/recurring"><span>🔁</span><b>Recurring expenses</b><span className="chev">›</span></Link></li>
          <li><button onClick={() => setCats(true)}><span>🏷️</span><b>Categories</b><span className="chev">›</span></button></li>
        </ul>
      </div>
      <div className="card more-user">
        <div>
          <b>{user?.name}</b>
          <div className="muted small-text">{user?.email}</div>
        </div>
        <button className="btn ghost small" onClick={signOut}>Log out</button>
      </div>
      {cats && <CategoryManager onClose={() => setCats(false)} />}
    </div>
  )
}
