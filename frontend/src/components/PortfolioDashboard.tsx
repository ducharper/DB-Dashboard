import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { amount, workspaceRequest } from '../lib/workspace'
import type { Portfolio, Position, PositionNote, StrategyRecord } from '../lib/workspace'

export default function PortfolioDashboard({ active }: { active: boolean }) {
  const [data, setData] = useState<Portfolio | null>(null)
  const [strategies, setStrategies] = useState<StrategyRecord[]>([])
  const [accountId, setAccountId] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [note, setNote] = useState<PositionNote | null>(null)
  const [noteTitle, setNoteTitle] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const snapshot = data?.snapshot
  const account = snapshot?.accounts.find(a => a.account === accountId) ?? snapshot?.accounts[0]
  async function load() {
    setError(''); setLoading(true)
    try {
      const [portfolio, library] = await Promise.all([workspaceRequest<Portfolio>('/portfolio'), workspaceRequest<StrategyRecord[]>('/strategies')])
      setData(portfolio); setStrategies(library)
    } catch (err) { setError((err as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    if (!active) return
    let current = true
    workspaceRequest<StrategyRecord[]>('/strategies').then(records => { if (current) setStrategies(records) }).catch(err => { if (current) setError((err as Error).message) })
    return () => { current = false }
  }, [active])
  async function refresh() {
    setBusy(true); setError(''); setMessage('')
    try { setData(await workspaceRequest<Portfolio>('/portfolio/refresh', 'POST')); setMessage('Snapshot refreshed and saved. TWS connection closed after download.') }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  function openNote(position: Position) {
    if (!account) return
    if (note && !window.confirm('Discard unsaved position-note changes?')) return
    setNote(data?.notes.find(n => n.account === account.account && n.contract_id === position.contract_id) ?? { account: account.account, contract_id: position.contract_id, strategy_id: null, thesis: '', invalidation: '' })
    setNoteTitle(position.symbol); setMessage('')
  }
  async function saveNote(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const saved = await workspaceRequest<PositionNote>('/portfolio/notes', 'PUT', note)
      setData(old => old ? { ...old, notes: [...old.notes.filter(n => n.account !== saved.account || n.contract_id !== saved.contract_id), saved] } : old)
      setNote(null); setMessage('Position note saved locally.')
    } catch (err) { setError((err as Error).message) }
    finally { setSaving(false) }
  }
  const tags = [['NetLiquidation', 'Account value'], ['TotalCashValue', 'Cash'], ['UnrealizedPnL', 'Unrealized P&L'], ['MaintMarginReq', 'Maintenance margin']]
  function metric(tag: string) {
    const values = account?.values.filter(v => v.tag === tag) ?? []
    const value = values.find(v => v.currency === 'BASE') ?? values.find(v => v.currency === account?.base_currency) ?? (values.length === 1 ? values[0] : undefined)
    return value ? amount(value.value, value.currency === 'BASE' ? account?.base_currency ?? 'BASE' : value.currency) : 'Unavailable'
  }
  return <section className="dashboard-page" aria-label="Portfolio overview">
    <header className="dashboard-heading"><div><span className="eyebrow">ACCOUNT WORKSPACE · READ ONLY</span><h1>Portfolio</h1><p>What you hold. Why you hold it. What needs your attention.</p></div><button disabled={busy || loading || saving} onClick={refresh}>{busy ? 'Reading TWS…' : 'Refresh from TWS'}</button></header>
    <div className="connection-strip"><span>{busy ? 'Connecting / downloading' : 'Saved snapshot · not streaming'}</span><span>{snapshot ? `Captured ${new Date(snapshot.captured_at).toLocaleString()}` : 'No snapshot saved yet'}</span></div>
    {error && <p className="error-message" role="alert">{error} {snapshot && 'Showing the previous saved snapshot.'} {!data && <button onClick={load}>Retry loading</button>}</p>}
    {message && <p className="footnote" role="status">{message}</p>}
    {loading && <p role="status">Loading your local workspace…</p>}
    {!loading && !snapshot && <section className="panel dashboard-card dashboard-empty"><h2>Bring your portfolio into the workspace.</h2><p>Open paper TWS, log in, and enable socket clients on port 7497. Keep Read-Only API enabled, then refresh. Positions and account values are saved only on this computer.</p><p>No orders will be placed. Without TWS, you can still use strategies, research, notes, and any saved snapshot.</p></section>}
    {account && <>
      <div className="account-toolbar"><label>Account<select disabled={saving || !!note} value={account.account} onChange={e => setAccountId(e.target.value)}>{snapshot?.accounts.map(a => <option key={a.account} value={a.account}>••••{a.account.slice(-4)}</option>)}</select></label><span className={account.mode === 'paper' ? 'complete-badge' : 'notice'}>{account.mode === 'paper' ? 'PAPER · DU account identifier' : 'LIVE / UNVERIFIED · confirm in TWS'}</span></div>
      <dl className="metrics-grid">{tags.map(([tag, label]) => <div className="metric-card" key={tag}><dt>{label}</dt><dd>{metric(tag)}</dd><span>TWS-reported snapshot</span></div>)}</dl>
      {snapshot?.warnings.map(warning => <p className="footnote" key={warning}>{warning}</p>)}
      <section className="panel dashboard-card"><div className="section-heading"><h2>Open positions <span className="count">{account.positions.length}</span></h2><span className="footnote">Values in instrument currency · not summed across currencies</span></div><div className="table-scroll"><table><thead><tr>{['Instrument', 'Quantity', 'Price', 'Market value', 'Unrealized P&L', 'Strategy / notes'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{account.positions.map(p => {
        const annotation = data?.notes.find(n => n.account === account.account && n.contract_id === p.contract_id)
        const strategy = strategies.find(s => s.id === annotation?.strategy_id)
        return <tr key={p.contract_id}><td><strong>{p.symbol}</strong><small>{p.security_type} · {p.currency} · #{p.contract_id}</small></td><td>{amount(p.quantity)}</td><td>{amount(p.market_price)}</td><td>{amount(p.market_value, p.currency)}</td><td className={p.unrealized_pnl == null ? '' : p.unrealized_pnl < 0 ? 'negative' : 'positive'}>{amount(p.unrealized_pnl, p.currency)}</td><td><button disabled={saving} onClick={() => openNote(p)}>{strategy?.name ?? 'Unassigned'} · {annotation ? 'Edit note' : 'Add note'}</button></td></tr>
      })}</tbody></table></div>{!account.positions.length && <p className="dashboard-empty">No open positions were reported for this account in this snapshot.</p>}<p className="footnote">Assignment is a manual label for the whole broker position. It does not split holdings between strategies or calculate strategy-level returns.</p></section>
    </>}
    {note && <form className="panel dashboard-card dashboard-editor position-editor" onSubmit={saveNote}><h2>{noteTitle} · Position plan</h2><fieldset disabled={saving}><label>Strategy<select value={note.strategy_id ?? ''} onChange={e => setNote({ ...note, strategy_id: e.target.value || null })}><option value="">Unassigned / discretionary</option>{strategies.map(s => <option key={s.id} value={s.id}>{s.name} · v{s.version} · {s.status}</option>)}</select></label><label>Thesis / reason for holding<textarea maxLength={10000} value={note.thesis} onChange={e => setNote({ ...note, thesis: e.target.value })} /></label><label>Invalidation / review plan<textarea maxLength={10000} value={note.invalidation} onChange={e => setNote({ ...note, invalidation: e.target.value })} /></label><div className="dashboard-actions"><button type="submit">{saving ? 'Saving…' : 'Save position note'}</button><button type="button" onClick={() => { if (window.confirm('Discard unsaved position-note changes?')) setNote(null) }}>Cancel</button></div></fieldset></form>}
    <p className="footnote">Refresh is manual. This view does not monitor risk limits or place orders. Saved notes remain attached to the account and contract if a position is closed and later reopened.</p>
  </section>
}
