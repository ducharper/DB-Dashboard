import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { workspaceRequest } from '../lib/workspace'
import type { StrategyRecord } from '../lib/workspace'

type Draft = Omit<StrategyRecord, 'id' | 'updated_at'>
const blank: Draft = { name: '', version: '1', status: 'research', rules: '', parameters: '', risk_plan: '' }
export default function StrategyLibrary() {
  const [records, setRecords] = useState<StrategyRecord[]>([])
  const [draft, setDraft] = useState<Draft>(blank)
  const [editing, setEditing] = useState<string | null>(null)
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loaded, setLoaded] = useState(false)
  async function load() {
    setError('')
    try { setRecords(await workspaceRequest<StrategyRecord[]>('/strategies')); setLoaded(true) }
    catch (err) { setError((err as Error).message) }
  }
  useEffect(() => { void load() }, [])
  function edit(record?: StrategyRecord) {
    if (visible && !window.confirm('Discard the unsaved editor contents?')) return
    setEditing(record?.id ?? null)
    setDraft(record ? { name: record.name, version: record.version, status: record.status, rules: record.rules, parameters: record.parameters, risk_plan: record.risk_plan } : { ...blank })
    setVisible(true); setMessage(''); setError('')
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const result = await workspaceRequest<StrategyRecord>(editing ? `/strategies/${editing}` : '/strategies', editing ? 'PUT' : 'POST', draft)
      setRecords(old => [result, ...old.filter(s => s.id !== result.id)])
      setVisible(false); setMessage('Strategy saved locally.')
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="dashboard-page" aria-label="Strategy library">
    <header className="dashboard-heading"><div><span className="eyebrow">RESEARCH → PAPER → LIVE</span><h1>Strategy library</h1><p>Your rules, rationale, and risk plans. Status labels do not activate trading.</p></div><button disabled={busy || !loaded} onClick={() => edit()}>New strategy +</button></header>
    {error && <p className="error-message" role="alert">{error} <button onClick={load}>Retry loading</button></p>}
    {message && <p role="status" className="footnote">{message}</p>}
    <div className="dashboard-columns"><section className="panel dashboard-card"><h2>Strategies <span className="count">{records.length}</span></h2>
      {!loaded && !error && <p role="status">Loading strategies…</p>}
      {loaded && !records.length && <p className="dashboard-empty">Start with one strategy you can explain. Record entry and exit rules, parameters, and when you would stop using it.</p>}
      <div className="strategy-records">{records.map(record => <button key={record.id} disabled={busy} onClick={() => edit(record)}><span><strong>{record.name}</strong><small>Version {record.version} · {record.status}</small></span><span aria-hidden="true">↗</span></button>)}</div>
      <p className="footnote">Records describe your strategies; they do not generate executable code. Version is a manual label; editing updates this record.</p></section>
      {visible ? <form className="panel dashboard-card dashboard-editor" onSubmit={save}><h2>{editing ? 'Edit strategy' : 'New strategy'}</h2><fieldset disabled={busy}>
        <label>Name<input required maxLength={120} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
        <div className="field-pair"><label>Version<input required maxLength={40} value={draft.version} onChange={e => setDraft({ ...draft, version: e.target.value })} /></label><label>Status<select value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value as Draft['status'] })}>{(['research', 'paper', 'live', 'paused', 'archived'] as const).map(s => <option key={s}>{s}</option>)}</select></label></div>
        <label>Rules & rationale<textarea maxLength={20000} value={draft.rules} onChange={e => setDraft({ ...draft, rules: e.target.value })} placeholder="What is the idea? When do you enter and exit?" /></label>
        <label>Parameters<textarea maxLength={10000} value={draft.parameters} onChange={e => setDraft({ ...draft, parameters: e.target.value })} placeholder="Instruments, windows, thresholds, time frame…" /></label>
        <label>Risk plan<textarea maxLength={10000} value={draft.risk_plan} onChange={e => setDraft({ ...draft, risk_plan: e.target.value })} placeholder="Sizing limits, invalidation criteria, review schedule…" /></label>
        <button type="submit">{busy ? 'Saving…' : 'Save strategy'}</button></fieldset></form> : <section className="panel dashboard-card"><span className="eyebrow">ONE RESEARCH WORKSPACE</span><h2>Keep the reasoning with the strategy.</h2><p className="dashboard-empty">Select a strategy to review its rules and risk plan. Assign it to observed positions from the Portfolio tab.</p><p className="footnote">Python backtests remain available in Research. NinjaTrader result importing is a next step—not connected yet.</p></section>}
    </div>
  </section>
}
