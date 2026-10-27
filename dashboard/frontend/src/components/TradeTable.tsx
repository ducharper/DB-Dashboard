import { useState } from 'react'
import type { BacktestResponse } from '../types/backtest'
import { money, percent, marketTime } from '../lib/format'
type Trade = BacktestResponse['trades'][number]
const columns: { key: keyof Trade; label: string }[] = [{ key: 'entry_date', label: 'Entry date' }, { key: 'exit_date', label: 'Exit date' }, { key: 'entry_price', label: 'Entry price' }, { key: 'exit_price', label: 'Exit price' }, { key: 'holding_period', label: 'Periods held' }, { key: 'net_return', label: 'Net return' }]
export default function TradeTable({ trades, symbol }: { trades: Trade[]; symbol: string }) {
  const [sort, setSort] = useState<keyof Trade>('entry_date')
  const [ascending, setAscending] = useState(true)
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(0)
  const filtered = trades.filter(t => filter === 'all' || (filter === 'wins' ? t.net_return > 0 : t.net_return < 0)).sort((a, b) => {
    const first = a[sort], second = b[sort]
    return (typeof first === 'number' && typeof second === 'number' ? first - second : String(first).localeCompare(String(second))) * (ascending ? 1 : -1)
  })
  const pages = Math.max(1, Math.ceil(filtered.length / 5)), current = Math.min(page, pages - 1)
  function download() {
    const csv = [columns.map(c => c.label).join(','), ...filtered.map(t => columns.map(c => t[c.key]).join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `${symbol.replace(/[^a-zA-Z0-9_-]/g, '_')}-trades.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section className="panel trade-panel"><div className="section-heading"><div><span className="eyebrow">TRADE LEDGER</span><h2>Behind the returns <span className="count">{trades.length}</span></h2></div><button className="quiet-button" disabled={!filtered.length} onClick={download}>Export CSV ↓</button></div>
    <div className="table-toolbar"><label>Show<select value={filter} onChange={e => { setFilter(e.target.value); setPage(0) }}><option value="all">All completed trades</option><option value="wins">Winning trades</option><option value="losses">Losing trades</option></select></label><span>{filtered.length} trades</span></div>
    <div className="table-scroll"><table><thead><tr>{columns.map(c => <th key={c.key} aria-sort={sort === c.key ? ascending ? 'ascending' : 'descending' : 'none'}><button onClick={() => { setSort(c.key); setAscending(sort === c.key ? !ascending : true); setPage(0) }}>{c.label} {sort === c.key ? ascending ? '↑' : '↓' : '↕'}</button></th>)}</tr></thead><tbody>{filtered.slice(current * 5, (current + 1) * 5).map(t => <tr key={`${marketTime(t.entry_date)}-${marketTime(t.exit_date)}`}><td>{marketTime(t.entry_date)}</td><td>{marketTime(t.exit_date)}</td><td>{money(t.entry_price)}</td><td>{money(t.exit_price)}</td><td>{t.holding_period}</td><td className={t.net_return >= 0 ? 'positive' : 'negative'}>{percent(t.net_return)}</td></tr>)}</tbody></table></div>
    {!filtered.length && <p className="table-empty">{trades.length ? 'No trades match this filter.' : 'No completed trades. The strategy may not have entered, or its final position may still be open.'}</p>}
    <div className="table-footer"><span>Completed trades only · open positions remain in portfolio performance.</span><div><button disabled={current === 0} onClick={() => setPage(current - 1)} aria-label="Previous trade page">←</button><span>{current + 1} / {pages}</span><button disabled={current >= pages - 1} onClick={() => setPage(current + 1)} aria-label="Next trade page">→</button></div></div><p className="footnote">Holding periods count trading intervals. Exported returns are decimals (0.05 = 5%).</p>
  </section>
}

