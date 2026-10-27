import type { BacktestRequest } from '../types/experiment'
import { strategyNames } from '../types/experiment'
import { money, percent } from '../lib/format'

export default function RunSettings({ request }: { request: BacktestRequest }) {
  const strategy = request.strategy
  const parameters = strategy.name === 'moving_average'
    ? [['Short window', `${strategy.short_window} periods`], ['Long window', `${strategy.long_window} periods`]]
    : strategy.name === 'momentum'
      ? [['Lookback', `${strategy.lookback} periods`]]
      : [['Mean window', `${strategy.mean_window} periods`], ['Entry distance', percent(strategy.entry_distance)], ['Exit distance', percent(strategy.exit_distance)]]
  const settings = [
    ['Bar size', request.bar_size === '1 min' ? '1 minute · New York time' : 'Daily'],
    ...(request.bar_size === '1 min' ? [['Execution', 'Next minute open; flat at 15:59'], ['Annualization', '252 sessions/year using daily returns']] : []),
    ['Price source', request.data_source === 'ibkr' ? 'IBKR · regular-session TRADES' : 'Yahoo Finance'],
    ...(request.data_source === 'ibkr' ? [['Primary exchange', request.ibkr_primary_exchange || 'SMART resolution']] : []),
    ['Symbol', request.symbol], ['Strategy', strategyNames[strategy.name]],
    ['Start date', request.start], ['End date (exclusive)', request.end],
    ...parameters, ['Initial capital', money(request.initial_cash)],
    ['Trading cost', `${request.cost_bps} bps`], ['Periods per year', String(request.periods_per_year)],
    ['Annual risk-free rate', percent(request.risk_free_rate)],
  ]
  return <details className="panel run-details">
    <summary>Run settings <span>Parameters used for this result</span></summary>
    <dl className="settings-summary">{settings.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
  </details>
}
