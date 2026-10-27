import { useEffect, useState } from 'react'
import { money, percent } from '../lib/format'

type Quote = { symbol: string; name: string; price: number | null; date: string | null; change: number | null; points: { date: string; close: number }[] }
type Snapshot = { items: Quote[]; fetched_at: string }

export default function MarketSnapshot() {
  const [data, setData] = useState<Snapshot | null>(null)
  const [selected, setSelected] = useState('SPY')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    let pending = false
    let controller: AbortController | null = null
    async function refresh() {
      if (pending || document.hidden) return
      controller = new AbortController()
      const request = controller
      pending = true
      setLoading(true)
      const timeout = setTimeout(() => request.abort(), 35000)
      try {
        const response = await fetch('/api/market-snapshot', { signal: request.signal })
        if (!response.ok) throw new Error()
        const result: Snapshot = await response.json()
        if (!Array.isArray(result.items) || !result.items.every(item => Array.isArray(item.points) && item.points.every(point => typeof point.date === 'string' && Number.isFinite(point.close)) && (item.change === null || Number.isFinite(item.change)) && (item.price === null || Number.isFinite(item.price)))) throw new Error()
        if (active) { setData(result); setError(false) }
      } catch { if (active) setError(true) }
      finally { clearTimeout(timeout); pending = false; if (active) setLoading(false) }
    }
    void refresh()
    const interval = setInterval(() => { void refresh() }, 300000)
    return () => { active = false; controller?.abort(); clearInterval(interval) }
  }, [revision])
  const quote = data?.items.find(item => item.symbol === selected)
  const points = quote?.points ?? []
  const low = Math.min(...points.map(point => point.close))
  const high = Math.max(...points.map(point => point.close))
  const path = points.map((point, i) => `${i ? 'L' : 'M'}${12 + i / Math.max(1, points.length - 1) * 776},${174 - (point.close - low) / (high - low || 1) * 148}`).join(' ')
  return <section className="market-snapshot" aria-label="Market snapshot" aria-busy={loading}>
    <div className="market-heading"><h2>Market snapshot</h2><button className="quiet-button" disabled={loading} onClick={() => setRevision(value => value + 1)}>{loading ? 'Updating…' : 'Refresh ↻'}</button></div>
    <div className="market-instruments" aria-label="Market instrument">
      {['SPY', 'QQQ', 'IWM'].map(symbol => {
        const item = data?.items.find(row => row.symbol === symbol)
        return <button key={symbol} aria-pressed={selected === symbol} onClick={() => setSelected(symbol)}><strong>{symbol}</strong><span>{item?.price != null ? money(item.price) : '—'}</span><small className={item?.change != null && item.change < 0 ? 'negative' : 'positive'}>{item?.change != null ? `${item.change >= 0 ? '+' : ''}${percent(item.change)}` : loading ? 'Loading' : 'Unavailable'}</small></button>
      })}
    </div>
    <div className="market-chart-heading"><span>{quote?.name ?? selected}</span><span>{quote?.date ? `As of ${quote.date}` : 'Latest available daily prices'}</span></div>
    <div className="market-plot">
      {points.length ? <svg key={`${selected}-${data?.fetched_at}`} viewBox="0 0 800 200" preserveAspectRatio="none" role="img" aria-label={`${selected}: one month of daily prices, ${points[0].date} through ${quote?.date}`}>
        {[30, 100, 174].map(y => <line key={y} x1="12" x2="788" y1={y} y2={y} className="grid-line" />)}
        <path className="market-area" d={`${path} L788,200 L12,200 Z`} />
        <path className="market-trace" d={path} pathLength="1" />
        <circle className="market-endpoint" cx="788" cy={174 - (points[points.length - 1].close - low) / (high - low || 1) * 148} r="3" />
      </svg> : <div className={loading ? 'market-loading' : 'market-unavailable'}>{loading ? 'Fetching market prices…' : 'Prices are unavailable. Your backtester is ready to use.'}</div>}
    </div>
    {points.length > 0 && <div className="market-dates"><span>{points[0].date}</span><span>{points[points.length - 1].date}</span></div>}
    <p className="market-disclosure">{error ? 'Refresh failed. Displayed prices may be out of date. ' : ''}Yahoo Finance · USD · Daily bars, may be delayed. Change vs. previous trading day. Refreshes every 5 min.</p>
  </section>
}
