import { useEffect, useRef, useState } from 'react'
import './kalshi.css'
import BitcoinResearch from './BitcoinResearch'
type Market = { ticker: string; event_ticker: string; title: string; yes_sub_title: string; close_time: string; status: string; yes_bid: number | null; yes_ask: number | null; no_bid: number | null; no_ask: number | null; volume: number | null; rules_primary: string; rules_secondary: string }
type Snapshot = { markets: Market[]; cursor: string; fetched_at: string }
type Result = { contracts: number; max_loss: number; allocation: number; expected_profit: number; conservative_profit: number; loss_probability: number; conservative_probability: number; break_even: number; profit_if_win: number; decision: string; reason: string }
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const pct = (n: number) => `${(n * 100).toFixed(1)}%`
const quote = (n: number | null) => n == null ? '—' : `${(n * 100).toFixed(1)}¢`
async function request<T>(path: string, signal: AbortSignal, body?: unknown): Promise<T> {
  const response = await fetch(`/api/kalshi/${path}`, { signal, ...(body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {}) })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check your inputs and try again.')
  return data
}
export default function KalshiDashboard({active}: {active: boolean}) {
  const [series, setSeries] = useState('KXBTC15M')
  const [query, setQuery] = useState({series: 'KXBTC15M', cursor: ''})
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [auto, setAuto] = useState(false)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('')
  const [side, setSide] = useState<'yes' | 'no'>('yes')
  const [now, setNow] = useState(() => Date.now())
  const [inputs, setInputs] = useState({probability: '', uncertainty: '5', cost_allowance: '2', bankroll: '1000', available_cash: '1000', existing_event_risk: '0', kelly_fraction: '25', trade_cap: '1', event_cap: '3'})
  const [result, setResult] = useState<Result | null>(null)
  const [sizing, setSizing] = useState(false)
  const sizingController = useRef<AbortController | null>(null)
  const [sizeError, setSizeError] = useState('')
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [active])
  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    setLoading(true); setError(''); setResult(null)
    request<Snapshot>(`markets?${new URLSearchParams(query)}`, controller.signal).then(data => {setSnapshot(data); setNow(Date.now())}).catch(e => {if (!controller.signal.aborted) setError(e.message)}).finally(() => {if (!controller.signal.aborted) setLoading(false)})
    return () => controller.abort()
  }, [active, query, refresh])
  useEffect(() => { if (!active || !auto || loading) return; const timer = window.setTimeout(() => setRefresh(n => n + 1), 30000); return () => clearTimeout(timer) }, [active, auto, loading, refresh])
  const market = snapshot?.markets.find(m => m.ticker === selected)
  const price = market?.[`${side}_ask`] ?? null
  const stale = !snapshot || now - Date.parse(snapshot.fetched_at) > 60000
  const closed = market ? Date.parse(market.close_time) <= now || !['open', 'active'].includes(market.status) : true
  const usable = !stale && !closed && !error && !loading && price != null
  useEffect(() => {sizingController.current?.abort(); setResult(null); setSizeError(''); return () => sizingController.current?.abort()}, [inputs, selected, side, snapshot])
  const labels: [keyof typeof inputs, string, string, string][] = [
    ['probability', 'Your YES probability (%)', '0', '100'], ['uncertainty', 'Probability haircut (percentage points)', '0', '100'],
    ['cost_allowance', 'Fees + slippage allowance (¢ / contract)', '0', '99'], ['bankroll', 'Dedicated Kalshi bankroll ($)', '1', '1000000000'],
    ['available_cash', 'Available cash ($)', '0', '1000000000'], ['existing_event_risk', 'Existing related-event maximum loss ($)', '0', '1000000000'],
    ['kelly_fraction', 'Fraction of Kelly (%)', '0.1', '100'], ['trade_cap', 'Maximum bankroll per trade (%)', '0.1', '100'], ['event_cap', 'Maximum bankroll per related event (%)', '0.1', '100']]
  return <section className="dashboard-page kalshi-page">
    <header className="dashboard-heading"><div><span className="eyebrow">PREDICTION MARKET RESEARCH</span><h1>Kalshi</h1><p>Explore contracts. Test a probability estimate. Size a hypothetical position.</p></div></header>
    <BitcoinResearch />
    <form className="kalshi-toolbar" onSubmit={e => {e.preventDefault(); setSnapshot(null); setSelected(''); setQuery({series: series.trim().toUpperCase(), cursor: ''})}}>
      <label>Series ticker<input value={series} onChange={e => setSeries(e.target.value)} placeholder="Blank for all markets" pattern="[A-Za-z0-9-]*" maxLength={100} /></label><button type="submit" disabled={loading}>Load markets</button><button type="button" disabled={loading} onClick={() => setRefresh(n => n + 1)}>Refresh</button>
      <label className="kalshi-check"><input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} />Refresh every 30 seconds</label>
    </form>
    <div className="connection-strip"><span>{loading ? 'Fetching public market data…' : snapshot ? `Fetched ${new Date(snapshot.fetched_at).toLocaleTimeString()} · ${stale ? 'STALE' : 'Recent snapshot'}` : 'No snapshot'}</span><span>REST polling · Not a streaming feed · No account connected</span></div>
    {error && <p role="alert" className="notice">{error} Previous data, if shown, is unavailable for sizing.</p>}
    <div className="kalshi-columns"><section className="panel dashboard-card"><h2>Market explorer</h2><label className="kalshi-search">Filter this page<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Team, title or ticker" /></label>
      <p className="field-help">Up to 100 contracts per page. Series filter searches Kalshi; text filters only the loaded page.</p>
      <div className="kalshi-markets">{snapshot?.markets.filter(m => `${m.title} ${m.yes_sub_title} ${m.ticker}`.toLowerCase().includes(search.toLowerCase())).map(m => <button key={m.ticker} className="kalshi-market" aria-pressed={selected === m.ticker} onClick={() => {setSelected(m.ticker); setInputs(v => ({...v, probability: ''}))}}><strong>{m.title || m.ticker}</strong><span>{m.yes_sub_title}</span><small>{m.ticker}</small><span>YES ask {quote(m.yes_ask)} · NO ask {quote(m.no_ask)}</span></button>)}</div>
      {snapshot && !snapshot.markets.length && <p className="dashboard-empty">No open binary markets in this series. Try another series ticker or leave it blank.</p>}
      <button disabled={loading || !snapshot?.cursor} onClick={() => {setSelected(''); setSnapshot(null); setQuery(v => ({...v, cursor: snapshot!.cursor}))}}>Next page</button>
    </section><section className="panel dashboard-card dashboard-editor"><h2>Trade lab</h2>{!market ? <p className="dashboard-empty">Select a contract to inspect its rules and evaluate YES or NO. No trained forecasting model is connected yet.</p> : <>
      <h3>{market.title}</h3><p className="field-help">{market.yes_sub_title} · Event: {market.event_ticker}</p><p className="field-help">Closes {new Date(market.close_time).toLocaleString()} · Volume {market.volume?.toLocaleString() ?? 'unavailable'}</p>
      <details><summary>Settlement rules</summary><p className="kalshi-rules">{market.rules_primary || 'Rules unavailable. Verify the contract on Kalshi.'}</p><p className="kalshi-rules">{market.rules_secondary}</p></details>
      <form onSubmit={async e => {e.preventDefault(); if (!usable || price == null) return; setSizing(true); setSizeError(''); const controller = new AbortController(); sizingController.current = controller; const timer = setTimeout(() => controller.abort(), 15000); try { const p = Number(inputs.probability)/100; setResult(await request<Result>('size', controller.signal, {probability: side === 'yes' ? p : 1-p, uncertainty: Number(inputs.uncertainty)/100, price, cost_allowance: Number(inputs.cost_allowance)/100, bankroll: Number(inputs.bankroll), available_cash: Number(inputs.available_cash), existing_event_risk: Number(inputs.existing_event_risk), kelly_fraction: Number(inputs.kelly_fraction)/100, trade_cap: Number(inputs.trade_cap)/100, event_cap: Number(inputs.event_cap)/100})) } catch(e) {if (!controller.signal.aborted) setSizeError(e instanceof Error ? e.message : 'Calculation failed')} finally {clearTimeout(timer); setSizing(false)} }}>
      <fieldset disabled={sizing}><label>Buy side<select value={side} onChange={e => setSide(e.target.value as 'yes' | 'no')}><option value="yes">YES</option><option value="no">NO</option></select></label><p>Ask {quote(price)} · Bid {quote(market[`${side}_bid`])}</p>
      <div className="kalshi-inputs">{labels.map(([key, label, min, max]) => <label key={key}>{label}<input type="number" required step="any" min={min} max={max} value={inputs[key]} onChange={e => setInputs(v => ({...v, [key]: e.target.value}))} /></label>)}</div>
      <p className="field-help">Defaults are editable research assumptions. Enter a probability supported by your own evidence. The haircut is a sensitivity assumption, not a confidence interval. Verify the market-specific fee; the allowance is not an exchange fee quote.</p>
      <button disabled={!usable || sizing} type="submit">{sizing ? 'Calculating…' : 'Evaluate hypothetical trade'}</button></fieldset></form>
      {!usable && <p className="notice">Refresh required, market closed, or executable ask unavailable. Sizing is disabled.</p>}
      {sizeError && <p role="alert" className="notice">{sizeError}</p>}
      {result && usable && <div aria-live="polite" className="kalshi-result"><h3>{result.decision} · {result.contracts} contracts</h3><p>{result.reason}</p><dl>{([
        ['Maximum loss incl. allowance', usd(result.max_loss)], ['Bankroll allocation', pct(result.allocation)], ['Expected profit', usd(result.expected_profit)], ['Haircut expected profit', usd(result.conservative_profit)], ['Probability of losing stake', pct(result.loss_probability)], ['Conservative side probability', pct(result.conservative_probability)], ['Break-even probability', pct(result.break_even)], ['Profit if side wins', usd(result.profit_if_win)]]).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></div>}
      <p className="field-help">Assumes a $1 binary payout held to settlement and fills at the displayed ask. Size is limited by fractional Kelly, trade/event caps and available cash. Order-book depth, actual fees, correlated portfolios and settlement exceptions are not modeled. Losing means losing the entire allocated stake. No trades are submitted.</p>
    </>}</section></div>
  </section>
}

