import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { submitBacktest } from '../lib/api'
import type { CompletedRun, StrategyConfig, BacktestRequest } from '../types/experiment'
type Props = { disabled?: boolean; initialRequest?: BacktestRequest; onResult: (run: CompletedRun) => void; onEdit: () => void; onRunning: (running: boolean) => void }
export default function BacktestForm({ disabled = false, initialRequest: r, onResult, onEdit, onRunning }: Props) {
  const [fields, setFields] = useState({ symbol: r?.symbol ?? 'AAPL', start: r?.start ?? '2020-01-01', end: r?.end ?? '2026-01-01', strategy: r?.strategy.name ?? 'moving_average', short: String(r?.strategy.name === 'moving_average' ? r.strategy.short_window : 20), long: String(r?.strategy.name === 'moving_average' ? r.strategy.long_window : 50), lookback: String(r?.strategy.name === 'momentum' ? r.strategy.lookback : 20), mean: String(r?.strategy.name === 'mean_reversion' ? r.strategy.mean_window : 20), entry: String(r?.strategy.name === 'mean_reversion' ? r.strategy.entry_distance * 100 : 5), exit: String(r?.strategy.name === 'mean_reversion' ? r.strategy.exit_distance * 100 : 1), cash: String(r?.initial_cash ?? 10000), costs: String(r?.cost_bps ?? 5), periods: String(r?.periods_per_year ?? 252), riskFree: String((r?.risk_free_rate ?? .04) * 100) })
  const [error, setError] = useState('')
  const [source, setSource] = useState<'yahoo' | 'ibkr'>(r ? r.data_source ?? 'yahoo' : 'ibkr')
  const [exchange, setExchange] = useState(r?.ibkr_primary_exchange ?? '')
  const [barSize, setBarSize] = useState<'1 day' | '1 min'>(r?.bar_size ?? '1 day')
  const [loading, setLoading] = useState(false)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  function update(key: keyof typeof fields, value: string) { setFields(old => ({ ...old, [key]: value })); setError(''); onEdit() }
  function numeric(key: keyof typeof fields, label: string, min: number, step = '1') {
    return <label>{label}<input type="number" required min={min} step={step} value={fields[key]} onChange={e => update(key, e.target.value)} /></label>
  }
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (controller.current || disabled) return
    setError('')
    const integer = (v: string) => v.trim() !== '' && Number.isInteger(Number(v)) && Number(v) > 0
    if (!fields.symbol.trim() || !fields.start || !fields.end || fields.start >= fields.end) { setError('Enter a symbol and a start date before the end date.'); return }
    let strategy: StrategyConfig
    if (fields.strategy === 'moving_average') {
      if (!integer(fields.short) || !integer(fields.long) || +fields.short >= +fields.long) { setError('Use positive whole-number windows; the short window must be smaller.'); return }
      strategy = { name: 'moving_average', short_window: +fields.short, long_window: +fields.long }
    } else if (fields.strategy === 'momentum') {
      if (!integer(fields.lookback)) { setError('Lookback must be a positive whole number.'); return }
      strategy = { name: 'momentum', lookback: +fields.lookback }
    } else {
      if (!integer(fields.mean) || !Number.isFinite(+fields.entry) || !Number.isFinite(+fields.exit) || fields.entry === '' || fields.exit === '' || +fields.entry <= 0 || +fields.entry >= 100 || +fields.exit < 0 || +fields.exit >= +fields.entry) { setError('Use a positive mean window, entry between 0% and 100%, and a nonnegative exit below entry.'); return }
      strategy = { name: 'mean_reversion', mean_window: +fields.mean, entry_distance: +fields.entry / 100, exit_distance: +fields.exit / 100 }
    }
    if (![fields.cash, fields.costs, fields.riskFree].every(v => v.trim() !== '' && Number.isFinite(+v)) || +fields.cash <= 0 || +fields.costs < 0 || +fields.riskFree <= -100 || !integer(fields.periods)) { setError('Check capital, costs, annualization, and risk-free rate.'); return }
    const request: BacktestRequest = { symbol: fields.symbol.trim().toUpperCase(), start: fields.start, end: fields.end, strategy, initial_cash: +fields.cash, cost_bps: +fields.costs, periods_per_year: +fields.periods, risk_free_rate: +fields.riskFree / 100 }
    request.data_source = source
    request.bar_size = barSize
    if (barSize === '1 min') {
      if (source !== 'ibkr') { setError('One-minute bars require Interactive Brokers.'); return }
      if ((Date.parse(fields.end) - Date.parse(fields.start)) / 86400000 > 31) { setError('Select at most 31 calendar days for minute bars.'); return }
      request.periods_per_year = 252
    }
    request.ibkr_primary_exchange = source === 'ibkr' ? exchange.trim().toUpperCase() : ''
    const abort = new AbortController()
    controller.current = abort
    setLoading(true); onRunning(true)
    try {
      const result = await submitBacktest(request, abort.signal)
      onResult({ id: result.run_id, request, result, completedAt: result.completed_at ?? new Date().toISOString() })
    } catch (err) {
      setError(abort.signal.aborted ? 'Stopped waiting. The server may still finish its calculation.' : err instanceof Error ? err.message : 'Backtest failed.')
    } finally { controller.current = null; setLoading(false); onRunning(false) }
  }
  return <form className="settings-panel panel" onSubmit={handleSubmit}>
    <div className="panel-heading"><h2>Backtest parameters</h2></div>
    <fieldset disabled={loading || disabled}>
      <div className="source-section">
        <div className="source-fields">
          <label>Price source<select value={source} onChange={e => { setSource(e.target.value as 'yahoo' | 'ibkr'); setError(''); onEdit() }}><option value="ibkr">Interactive Brokers · TWS</option><option value="yahoo">Yahoo Finance</option></select></label>
          {source === 'ibkr' && <label>Primary exchange · optional<input maxLength={30} pattern="[A-Za-z0-9.]*" placeholder="NASDAQ or NYSE" value={exchange} onChange={e => { setExchange(e.target.value); setError(''); onEdit() }} /></label>}
        </div>
        {source === 'ibkr' && <details className="source-guidance"><summary>TWS connection & data notes</summary><p>Keep paper TWS open on port 7497 with Read-Only API enabled. US stocks & ETFs · USD · regular sessions. Split-adjusted prices exclude dividends. Long downloads may take several minutes.</p></details>}
      </div>
      <section className="form-section" aria-labelledby="market-heading"><h3 id="market-heading">Market & dates</h3><label>Symbol<input required maxLength={30} value={fields.symbol} onChange={e => update('symbol', e.target.value)} autoCapitalize="characters" spellCheck={false} /></label>
      <div className="field-pair"><label>Start date<input type="date" required value={fields.start} onChange={e => update('start', e.target.value)} /></label><label>End date<input type="date" required value={fields.end} onChange={e => update('end', e.target.value)} /></label></div>
      <label>Bar size<select value={barSize} onChange={e => { setBarSize(e.target.value as '1 day' | '1 min'); setError(''); onEdit() }}><option value="1 day">Daily</option><option value="1 min" disabled={source !== 'ibkr'}>1 minute · IBKR</option></select></label>
      <p className="field-help">End date is exclusive. {barSize === '1 min' ? 'Completed sessions only · maximum 31 calendar days · times shown in New York time. Holidays, early closes and incomplete sessions stop the run.' : 'Daily prices.'}</p>
      </section><section className="form-section" aria-labelledby="strategy-heading"><h3 id="strategy-heading">Strategy</h3><label>Strategy<select value={fields.strategy} onChange={e => update('strategy', e.target.value)}><option value="moving_average">Moving average crossover</option><option value="momentum">Momentum</option><option value="mean_reversion">Mean reversion</option></select></label>
      <div className="parameter-box">
        {fields.strategy === 'moving_average' ? <><p>Invest when the short average is above the long average.</p><div className="field-pair">{numeric('short', 'Short window · bars', 1)}{numeric('long', 'Long window · bars', 1)}</div></> : fields.strategy === 'momentum' ? <><p>Invest when price exceeds its value one lookback ago.</p>{numeric('lookback', 'Lookback · trading periods', 1)}</> : <><p>Buy below the rolling mean; exit as price recovers toward it.</p>{numeric('mean', 'Mean window · trading periods', 1)}<div className="field-pair">{numeric('entry', 'Entry distance %', 0, 'any')}{numeric('exit', 'Exit distance %', 0, 'any')}</div></>}
      </div>
      </section><section className="form-section" aria-labelledby="capital-heading"><h3 id="capital-heading">Capital & costs</h3><div className="field-pair">{numeric('cash', 'Initial capital · USD', 0.01, 'any')}{numeric('costs', 'Cost · basis points', 0, 'any')}</div>
      <p className="field-help">5 bps = 0.05% per unit of turnover.</p>
      <div className="annualization-fields"><div className="field-pair">{barSize === '1 min' ? <p>Risk metrics use daily compounded returns and 252 sessions/year. Annualized metrics require at least 20 sessions.</p> : numeric('periods', 'Periods / year', 1)}{numeric('riskFree', 'Risk-free rate %', -99.99, 'any')}</div></div></section>

    </fieldset>
    {loading && <button type="button" className="quiet-button" onClick={() => controller.current?.abort()}>Stop waiting</button>}
    <div role="status" className="form-status">{loading ? 'Downloading prices and calculating performance…' : ''}</div>
    {error && <p role="alert" className="error-message">{error}</p>}
    <div className="parameter-footer"><details className="assumptions"><summary>Simulation assumptions</summary><p>{barSize === '1 min' ? 'Long or flat · completed-bar signals fill at the next minute open · liquidate at 15:59 open · indicators restart each session. Windows count minutes. Fills are estimates; costs apply to buys and sells.' : 'Long or flat · one-period signal delay · close-to-close returns.'} Strategy costs included; buy-and-hold shown before costs and includes overnight exposure.</p></details><button className="primary-button" type="submit" disabled={loading || disabled}>{loading ? 'Running experiment…' : 'Run backtest'} <span aria-hidden="true">↗</span></button></div>
  </form>
}

