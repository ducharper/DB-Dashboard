export const money = (v: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v)
export const percent = (v: number) => `${(v * 100).toFixed(2)}%`
export const marketTime = (v: string) => v.includes('T') ? `${v.slice(0, 10)} ${v.slice(11, 16)} ET` : v
const percentages = new Set(['Time in Market', 'Total Return', 'Annualized Return', 'Benchmark Return', 'Annualized Volatility', 'Max Drawdown'])
export function metric(name: string, v: number | null | undefined) {
  if (v == null || !Number.isFinite(v)) return 'N/A'
  if (percentages.has(name)) return percent(v)
  return v.toFixed(name === 'Number of Market Entries' ? 0 : 2)
}
