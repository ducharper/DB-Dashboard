export type StrategyRecord = { id: string; name: string; version: string; status: 'research' | 'paper' | 'live' | 'paused' | 'archived'; rules: string; parameters: string; risk_plan: string; updated_at: string }
export type Position = { contract_id: number; symbol: string; security_type: string; currency: string; quantity: number; market_price: number | null; market_value: number | null; average_cost: number | null; unrealized_pnl: number | null; realized_pnl: number | null }
export type Account = { account: string; mode: string; base_currency: string | null; values: { tag: string; currency: string; value: number | null }[]; positions: Position[] }
export type PositionNote = { account: string; contract_id: number; strategy_id: string | null; thesis: string; invalidation: string; updated_at?: string }
export type Portfolio = { snapshot: { id: string; captured_at: string; source: string; warnings: string[]; accounts: Account[] } | null; notes: PositionNote[] }

export async function workspaceRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  let response: Response
  try { response = await fetch(`/api${path}`, { method, ...(body !== undefined ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) }) }
  catch { throw new Error('Cannot reach the local app. Check the launcher and try again.') }
  const result = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof result?.detail === 'string' ? result.detail : `Request failed (${response.status}). Check the fields and try again.`)
  if (!result) throw new Error('The app returned an unreadable response.')
  return result as T
}

export function amount(value: number | null | undefined, currency = '') {
  return value == null ? 'Unavailable' : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${currency ? ` ${currency}` : ''}`
}
