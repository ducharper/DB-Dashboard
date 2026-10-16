import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { BacktestResponse } from '../types/backtest'
import { money, percent, marketTime } from '../lib/format'

type Props = { equity: BacktestResponse['equity']; initialCash: number }
export default function PerformanceChart({ equity, initialCash }: Props) {
  const [mode, setMode] = useState<'equity' | 'return' | 'drawdown'>('equity')
  const [start, setStart] = useState(equity[0].date.slice(0, 10))
  const [end, setEnd] = useState(equity[equity.length - 1].date.slice(0, 10))
  const [cursor, setCursor] = useState<number | null>(null)
  const [width, setWidth] = useState(700)
  const [height, setHeight] = useState(310)
  const container = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const observer = new ResizeObserver(entries => {
      setWidth(Math.max(280, entries[0].contentRect.width))
      setHeight(Math.max(100, entries[0].contentRect.height))
    })
    if (container.current) observer.observe(container.current)
    return () => observer.disconnect()
  }, [])
  let peak = initialCash, benchmarkPeak = initialCash
  // Peaks are calculated over the full run, before applying the visible date range.
  const all = []
  for (const p of equity) {
    peak = Math.max(peak, p.strategy); benchmarkPeak = Math.max(benchmarkPeak, p.benchmark)
    all.push({ ...p, a: mode === 'equity' ? p.strategy : mode === 'return' ? p.strategy / initialCash - 1 : p.strategy / peak - 1,
      b: mode === 'equity' ? p.benchmark : mode === 'return' ? p.benchmark / initialCash - 1 : p.benchmark / benchmarkPeak - 1 })
  }
  const points = all.filter(p => p.date.slice(0, 10) >= start && p.date.slice(0, 10) <= end)
  const left = 76, right = width - 16, top = 24, bottom = height - 38
  let low = Infinity, high = -Infinity
  for (const p of points) { low = Math.min(low, p.a, p.b); high = Math.max(high, p.a, p.b) }
  if (!points.length) { low = 0; high = 1 }
  const pad = (high - low || Math.abs(high) || 1) * 0.08
  low -= pad; high += pad
  const x = (i: number) => points.length === 1 ? (left + right) / 2 : left + i / (points.length - 1) * (right - left)
  const y = (v: number) => bottom - (v - low) / (high - low) * (bottom - top)
  const line = (key: 'a' | 'b') => points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(p[key]).toFixed(2)}`).join(' ')
  const selected = cursor === null ? points.length - 1 : Math.min(cursor, points.length - 1)
  const point = points[selected]
  const format = mode === 'equity' ? money : percent
  const axisFormat = (v: number) => mode === 'equity' ? new Intl.NumberFormat('en-US', { notation: 'compact', style: 'currency', currency: 'USD', maximumFractionDigits: 1 }).format(v) : `${(v * 100).toFixed(1)}%`
  return <section className="panel chart-panel">
    <div className="section-heading"><div><span className="eyebrow">PERFORMANCE</span><h2>Strategy / Buy & hold</h2></div><div className="segmented" aria-label="Chart measure">{(['equity', 'return', 'drawdown'] as const).map(m => <button key={m} aria-pressed={mode === m} onClick={() => setMode(m)}>{m === 'equity' ? 'Value' : m === 'return' ? 'Return' : 'Drawdown'}</button>)}</div></div>
    <div className="chart-controls"><label>From<input aria-label="Chart start date" type="date" min={equity[0].date.slice(0, 10)} max={end} value={start} onChange={e => { setStart(e.target.value); setCursor(null) }} /></label><label>To<input aria-label="Chart end date" type="date" min={start} max={equity[equity.length - 1].date.slice(0, 10)} value={end} onChange={e => { setEnd(e.target.value); setCursor(null) }} /></label><button className="quiet-button" onClick={() => { setStart(equity[0].date.slice(0, 10)); setEnd(equity[equity.length - 1].date.slice(0, 10)); setCursor(null) }}>Full range</button></div>
    <div className="chart-readout"><span>{point ? marketTime(point.date) : 'No observations'}</span><span><i className="swatch strategy" />Strategy <strong>{point ? format(point.a) : '—'}</strong></span><span><i className="swatch benchmark" />Buy & hold <strong>{point ? format(point.b) : '—'}</strong></span></div>
    <div className="chart-interaction" onPointerLeave={event => { if (!event.currentTarget.contains(document.activeElement)) setCursor(null) }}>
    <div ref={container} className="chart-container">
      {points.length ? <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${mode} chart for strategy and buy-and-hold. Use the observation slider for exact values.`} onPointerMove={e => { const bounds = e.currentTarget.getBoundingClientRect(); const local = (e.clientX - bounds.left) * width / bounds.width; setCursor(Math.max(0, Math.min(points.length - 1, Math.round((local - left) / (right - left) * (points.length - 1))))) }}>
        {Array.from({ length: 5 }, (_, i) => { const v = low + (high - low) * i / 4; return <g key={i}><line x1={left} x2={right} y1={y(v)} y2={y(v)} className="grid-line" /><text x={left - 10} y={y(v) + 4} textAnchor="end">{axisFormat(v)}</text></g> })}
        <path d={line('b')} className="benchmark-line" /><path d={line('a')} className="strategy-line" />
        {[...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])].map(i => <text key={i} x={x(i)} y={height - 10} textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{marketTime(points[i].date)}</text>)}
        {point && <><line x1={x(selected)} x2={x(selected)} y1={top} y2={bottom} className="cursor-line" /><circle cx={x(selected)} cy={y(point.a)} r="4" className="strategy-dot" /><circle cx={x(selected)} cy={y(point.b)} r="4" className="benchmark-dot" /></>}
      </svg> : <div className="chart-empty">No trading observations in this range. Adjust the dates.</div>}
    </div>
    {points.length > 1 && <input className="observation-slider" type="range" aria-label="Inspect chart observation" aria-valuetext={point ? `${point.date}, strategy ${format(point.a)}, buy and hold ${format(point.b)}` : undefined} style={{ '--plot-left': `${left}px`, '--plot-right': `${width - right}px`, '--scrub-progress': `${Math.max(0, selected) / (points.length - 1) * 100}%` } as CSSProperties} min={0} max={points.length - 1} value={Math.max(0, selected)} onChange={e => setCursor(+e.target.value)} />}
    </div>
    <p className="footnote">{mode === 'drawdown' ? 'Drawdown from the running peak of the full backtest.' : mode === 'return' ? 'Cumulative return from the original starting capital.' : 'Portfolio value in USD.'} Dates are spaced by trading observation. Intraday labels use New York time and identify the start of each minute; values reflect its close. Hover or use the slider to inspect.</p>
  </section>
}

