import { useState } from 'react'

type Entry = { id: string; title: string; body: string; updatedAt: string }
const storageKey = 'backtester.journal.v1'
function readEntries(): { entries: Entry[]; error: string } {
  try {
    const raw = localStorage.getItem(storageKey)
    const entries: unknown = raw ? JSON.parse(raw) : []
    if (!Array.isArray(entries) || !entries.every(entry => entry && ['id', 'title', 'body', 'updatedAt'].every(key => typeof entry[key] === 'string'))) throw new Error()
    return { entries, error: '' }
  } catch { return { entries: [], error: 'Could not read your journal. Reload or check browser storage access. Existing data has not been replaced.' } }
}

export default function Journal() {
  const [initial] = useState(readEntries)
  const [entries, setEntries] = useState(initial.entries)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState(initial.error)
  const active = entries.find(entry => entry.id === selected)
  function persist(next: Entry[]) {
    setEntries(next)
    try { localStorage.setItem(storageKey, JSON.stringify(next)); setError(''); return true }
    catch { setError('Changes are only in memory. Browser storage could not save them. Keep this page open and copy your notes before leaving.'); return false }
  }
  function create() {
    const entry = { id: crypto.randomUUID(), title: '', body: '', updatedAt: new Date().toISOString() }
    persist([entry, ...entries]); setSelected(entry.id)
  }
  function update(field: 'title' | 'body', value: string) {
    persist(entries.map(entry => entry.id === selected ? { ...entry, [field]: value, updatedAt: new Date().toISOString() } : entry))
  }
  return <section className="journal panel" aria-label="Research journal">
    <div className="journal-heading"><div><span className="eyebrow">RESEARCH NOTES</span><h2>Journal</h2></div><button disabled={!!initial.error} onClick={create}>New idea +</button></div>
    {error && <p className="error-message" role="alert">{error}</p>}
    <div className="journal-body"><aside className="journal-list" aria-label="Journal entries">
      {entries.length ? entries.map(entry => <button key={entry.id} aria-current={selected === entry.id ? 'true' : undefined} onClick={() => setSelected(entry.id)}><strong>{entry.title.trim() || 'Untitled idea'}</strong><span>{entry.body.trim().slice(0, 65) || 'Start with a hypothesis…'}</span></button>) : <p>Your ideas start here.</p>}
    </aside>
    {active ? <div className="journal-editor"><label>Title<input value={active.title} placeholder="Give your idea a name" onChange={event => update('title', event.target.value)} /></label><label className="journal-notes">Notes<textarea aria-label="Notes" value={active.body} placeholder="What’s your hypothesis? What would you test? What did you learn?" onChange={event => update('body', event.target.value)} /></label><button className="journal-save" onClick={() => { if (persist(entries)) setSelected(null) }}>Save & close</button><p className="footnote" role="status">{error ? 'Not saved to browser storage.' : 'Saved in this browser · Stored separately from saved backtests'}</p></div> : <div className="journal-empty"><h2>A place for the thinking.</h2><p>Capture hypotheses, observations, and questions for your next backtest.</p><button disabled={!!initial.error} onClick={create}>{entries.length ? 'Write another idea ↗' : 'Write your first idea ↗'}</button><p className="footnote">Notes stay in this browser. Clearing browser data removes them.</p></div>}
    </div>
  </section>
}

export function JournalReference() {
  const [data] = useState(readEntries)
  const [selected, setSelected] = useState(data.entries[0]?.id ?? '')
  const active = data.entries.find(entry => entry.id === selected)
  return <aside className="journal-reference" aria-label="Quick journal reference"><span className="eyebrow">IDEAS AT HAND</span><h2>Journal</h2>{data.error ? <p role="alert">{data.error}</p> : data.entries.length ? <><label>Idea<select aria-label="Idea" value={selected} onChange={event => setSelected(event.target.value)}>{data.entries.map(entry => <option key={entry.id} value={entry.id}>{entry.title.trim() || 'Untitled idea'}</option>)}</select></label><div className="reference-note">{active?.body || 'No notes yet.'}</div><p className="footnote">Reference only · Edit entries in the full journal.</p></> : <p>No ideas saved yet. Add one from the Journal tab.</p>}</aside>
}
