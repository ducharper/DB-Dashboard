import type { BacktestResponse } from '../types/backtest'
import type { BacktestRequest } from '../types/experiment'
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const date = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))?$/.test(v) && Number.isFinite(Date.parse(v))
export function isBacktestResponse(v: unknown): v is BacktestResponse {
  if (!object(v) || !object(v.summary) || !Array.isArray(v.equity) || !Array.isArray(v.trades)) return false
  if (v.data_info != null) {
    const info = v.data_info
    if (!object(info) || !['ibkr', 'yahoo'].includes(String(info.source)) || typeof info.price_basis !== 'string' || !date(info.first_date) || !date(info.last_date) || !finite(info.bar_count) || typeof info.fetched_at !== 'string' || !Array.isArray(info.warnings) || !info.warnings.every(w => typeof w === 'string')) return false
  }
  return Object.values(v.summary).every(n => n === null || finite(n)) && v.equity.length > 0 &&
    v.equity.every(p => object(p) && date(p.date) && finite(p.strategy) && finite(p.benchmark)) &&
    v.trades.every(t => object(t) && date(t.entry_date) && date(t.exit_date) && finite(t.entry_price) && finite(t.exit_price) && finite(t.net_return) && finite(t.holding_period))
}
export async function submitBacktest(request: BacktestRequest, signal: AbortSignal): Promise<BacktestResponse> {
  let response: Response
  try { response = await fetch('/api/backtests', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal }) }
  catch (error) { if (signal.aborted) throw error; throw new Error('Unable to reach the API. Check that the launcher is running (or your development API on port 8000).') }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = object(body) ? body.detail : null
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) throw new Error(detail.filter(object).map(item => `${Array.isArray(item.loc) ? item.loc.slice(1).join(' → ') : 'Request'}: ${String(item.msg)}`).join('; ') || 'The API rejected these settings.')
    throw new Error(`Backtest failed (${response.status}). Check the API terminal and try again.`)
  }
  if (!isBacktestResponse(body)) throw new Error('The API returned incomplete or invalid results. Check the API terminal.')
  return body
}
