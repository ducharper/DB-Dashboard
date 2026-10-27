import { useEffect, useState } from 'react'
type ResearchStatus = {
  running: boolean
  configuration: { credentials_configured: boolean; signing_available: boolean; websocket_available: boolean }
  session: { id: string; state: string; started_ms: number; ended_ms: number | null; error: string | null } | null
  counts: Record<string, number>
  latest_brti: { source_ms: number; received_ms: number; value: number } | null
  windows: { end_ms: number; observed_seconds: number; missing_seconds: number; conflicts: number; complete: boolean; observed_average: number | null }[]
  metadata: { ticker: string; title?: string; rules_primary?: string; floor_strike?: number; close_time?: string }[]
}
async function call(path = '', minutes?: number): Promise<ResearchStatus> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch(`/api/kalshi/btc-research${path}`, {signal: controller.signal, ...(path ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(path === '/start' ? {minutes} : {})} : {})})
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Recorder request failed.')
    return data
  } finally {clearTimeout(timeout)}
}
const time = (ms: number) => new Date(ms).toLocaleString()
const dollars = (value: number) => value.toLocaleString('en-US', {style:'currency', currency:'USD'})
export default function BitcoinResearch() {
  const [status, setStatus] = useState<ResearchStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [minutes, setMinutes] = useState(30)
  const [revision, setRevision] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      try {const next = await call(); if (!disposed) {setStatus(next); setError(''); setNow(Date.now())}}
      catch(e) {if (!disposed) setError(e instanceof Error ? e.message : 'Recorder unavailable')}
      finally {if (!disposed) timer = setTimeout(refresh, 2000)}
    }
    void refresh()
    return () => {disposed = true; clearTimeout(timer)}
  }, [revision])
  async function action(path: '/start' | '/stop') {
    setBusy(true); setError('')
    try {await call(path, minutes); setRevision(n => n+1)}
    catch(e) {setError(e instanceof Error ? e.message : 'Recorder request failed')}
    finally {setBusy(false)}
  }
  const ready = status && Object.values(status.configuration).every(Boolean)
  const age = status?.latest_brti ? (now-status.latest_brti.source_ms)/1000 : null
  const fresh = !error && status?.running && status.session?.state === 'recording' && age !== null && age >= 0 && age <= 5
  return <section className="panel dashboard-card btc-research" aria-label="Bitcoin 15-minute research">
    <div className="dashboard-heading"><div><span className="eyebrow">KXBTC15M / DATA COLLECTION</span><h2>Bitcoin settlement research</h2><p>Record BRTI observations and contract order books before testing an edge.</p></div><span className="complete-badge">{status?.session?.state ?? 'Not started'}</span></div>
    <p className="field-help">The experiment compares the final-minute average with the opening reference. A spot-price move alone is not a forecast of the settlement average.</p>
    <div className="kalshi-toolbar"><label>Recording duration<select value={minutes} onChange={e => setMinutes(Number(e.target.value))} disabled={busy || status?.running}><option value={15}>15 minutes</option><option value={30}>30 minutes</option><option value={60}>1 hour</option><option value={120}>2 hours</option></select></label>
      <button onClick={() => void action('/start')} disabled={busy || !ready || status?.running}>Start recording</button><button onClick={() => void action('/stop')} disabled={busy || !status?.running}>Stop recording</button></div>
    {error && <p className="notice" role="alert">{error}</p>}
    {status?.session?.error && <p className="notice">{status.session.error}</p>}
    {!ready && status && <div className="btc-setup"><h3>Connect the research feed</h3><p>{!status.configuration.signing_available || !status.configuration.websocket_available ? 'Recorder dependencies need installation. ' : ''}{!status.configuration.credentials_configured ? 'Local API credentials are not configured.' : ''}</p><p>Install <code>requirements-kalshi.txt</code> in the project virtual environment. Set <code>KALSHI_API_KEY_ID</code> and <code>KALSHI_PRIVATE_KEY_PATH</code> in your local environment. Keep the PEM file outside the repository. The recorder reads the key from a local file; it never sends it to the browser. Restart the launcher after configuring it.</p></div>}
    <dl className="metrics-grid"><div className="metric-card"><dt>Latest recorded BRTI</dt><dd>{status?.latest_brti ? dollars(status.latest_brti.value) : '--'}</dd><span>{fresh ? 'Recent source tick' : 'Waiting / stale / offline'}{age !== null ? ` | ${Math.max(0,age).toFixed(0)}s old` : ''}</span></div>
      <div className="metric-card"><dt>BRTI frames</dt><dd>{status?.counts.cfbenchmarks_value ?? 0}</dd><span>Raw arrivals, not unique seconds</span></div><div className="metric-card"><dt>Book frames</dt><dd>{(status?.counts.orderbook_delta ?? 0)+(status?.counts.orderbook_snapshot ?? 0)}</dd><span>Snapshots + incremental changes</span></div><div className="metric-card"><dt>Sequence gaps</dt><dd>{status?.counts.sequence_gap ?? 0}</dd><span>Reconnects force fresh snapshots</span></div></dl>
    {status?.latest_brti && <p className="field-help">Source: {time(status.latest_brti.source_ms)} | Received locally: {time(status.latest_brti.received_ms)}</p>}
    <h3>Final-minute observation coverage</h3><p className="field-help">Most recent four quarter-hour windows. A running window is naturally incomplete. Missing seconds are never filled; an observed average is not an official settlement value.</p>
    <div className="btc-window-grid">{status?.windows.map(window => <div key={window.end_ms}><strong>{time(window.end_ms)}</strong><span>{window.observed_seconds}/60 seconds | {window.conflicts ? `${window.conflicts} conflicting observations` : window.complete ? 'Complete observation window' : 'Incomplete'}</span><span>Observed average: {window.observed_average == null ? '--' : dollars(window.observed_average)}</span></div>)}</div>
    {status?.metadata.length ? <details><summary>Recorded contract metadata ({status.metadata.length})</summary>{status.metadata.map(m => <div className="btc-contract" key={m.ticker}><strong>{m.title ?? m.ticker}</strong><p>{m.ticker} | API strike: {m.floor_strike ?? 'unavailable'} | Close: {m.close_time ?? 'unavailable'}</p><p>{m.rules_primary || 'Rules not returned; consult the contract.'}</p></div>)}</details> : null}
    <p className="field-help">Recording continues while you use other dashboard tabs, until its timer ends, you stop it, or the server exits. Stored locally in a separate research database. This milestone records data only: no model probabilities, simulated fills or live orders.</p>
  </section>
}
