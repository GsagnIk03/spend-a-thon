import { useState, type FormEvent } from 'react'
import { api, notifyExpensesChanged } from '../api'
import { useMeta } from '../hooks'
import type { Category } from '../types'
import { cx } from '../utils'
import { ErrorNote, Modal } from './ui'

const EMOJIS = ['🚬', '☕', '🍵', '🍺', '🍔', '🥤', '💊', '🩺', '🐶', '👶', '🏋️', '📱',
  '💻', '🎮', '🧺', '🔧', '🚗', '🏍️', '🅿️', '💈', '👕', '🧾', '🙏', '🎉']
const COLORS = ['#f97316', '#22c55e', '#eab308', '#ec4899', '#06b6d4', '#6366f1', '#ef4444',
  '#8b5cf6', '#0ea5e9', '#14b8a6', '#64748b', '#d946ef', '#84cc16', '#a16207']

/** Create (no `category`) or edit a custom category. */
export default function CategoryEditor({ category, onClose }: {
  category?: Category
  onClose: (saved?: Category) => void
}) {
  const { reload } = useMeta()
  const [label, setLabel] = useState(category?.label ?? '')
  const [emoji, setEmoji] = useState(category?.emoji ?? '🧾')
  const [color, setColor] = useState(category?.color ?? COLORS[Math.floor(Math.random() * COLORS.length)])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (!label.trim()) return setError('Give it a name')
    setBusy(true)
    setError(null)
    try {
      const body = { label: label.trim(), emoji: emoji.trim() || '🧾', color }
      const saved = category ? await api.updateCategory(category.id, body) : await api.createCategory(body)
      await reload()
      if (category) notifyExpensesChanged()
      onClose(saved)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  async function remove() {
    if (!category || !confirm(`Delete "${category.label}"? Its expenses will move to "Other".`)) return
    setBusy(true)
    try {
      await api.deleteCategory(category.id)
      await reload()
      notifyExpensesChanged()
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Modal title={category ? 'Edit category' : 'New category'} onClose={() => onClose()} footer={
      <>
        {category && <button type="button" className="btn danger-ghost" onClick={remove} disabled={busy}>Delete</button>}
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={() => onClose()} disabled={busy}>Cancel</button>
        <button type="submit" form="category-form" className="btn primary" disabled={busy}>
          {busy ? 'Saving…' : category ? 'Save' : 'Create'}
        </button>
      </>
    }>
      <form id="category-form" className="form" onSubmit={submit}>
        <div className="cat-preview">
          <span className="cat-badge md" style={{ background: `${color}22`, color }}>{emoji}</span>
          <input autoFocus value={label} maxLength={30} placeholder="e.g. Cigarettes, Tea, Medicines"
            onChange={(e) => setLabel(e.target.value)} aria-label="Category name" />
        </div>
        <div className="field">
          <span className="field-label">Icon <span className="muted">(pick one or type any emoji)</span></span>
          <div className="emoji-grid">
            {EMOJIS.map((em) => (
              <button key={em} type="button" className={cx('emoji-btn', emoji === em && 'active')} onClick={() => setEmoji(em)}>
                {em}
              </button>
            ))}
            <input className="emoji-input" value={emoji} maxLength={4} onChange={(e) => setEmoji(e.target.value)}
              aria-label="Custom emoji" />
          </div>
        </div>
        <div className="field">
          <span className="field-label">Colour</span>
          <div className="swatches">
            {COLORS.map((c) => (
              <button key={c} type="button" className={cx('swatch', color === c && 'active')}
                style={{ background: c }} onClick={() => setColor(c)} aria-label={c} />
            ))}
          </div>
        </div>
        <ErrorNote message={error} />
      </form>
    </Modal>
  )
}

/** List of all categories; custom ones can be edited or deleted. */
export function CategoryManager({ onClose }: { onClose: () => void }) {
  const { categories } = useMeta()
  const [editing, setEditing] = useState<Category | 'new' | null>(null)
  const custom = categories.filter((c) => c.custom)
  const builtIn = categories.filter((c) => !c.custom)
  return (
    <Modal title="Categories" onClose={onClose} footer={
      <>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setEditing('new')}>+ New category</button>
      </>
    }>
      <div className="form">
        <div>
          <h3 className="section-label">Your categories</h3>
          {custom.length === 0 ? (
            <p className="muted small-text">None yet. Add things you want to track separately — cigarettes, tea, medicines, pet care…</p>
          ) : (
            <ul className="cat-manage">
              {custom.map((c) => (
                <li key={c.id}>
                  <span className="cat-badge sm" style={{ background: `${c.color}22` }}>{c.emoji}</span>
                  <span className="grow">{c.label}</span>
                  <button className="link-btn" onClick={() => setEditing(c)}>Edit</button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="section-label">Built in</h3>
          <div className="chips">
            {builtIn.map((c) => <span key={c.id} className="chip static">{c.emoji} {c.label}</span>)}
          </div>
        </div>
      </div>
      {editing && <CategoryEditor category={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </Modal>
  )
}
