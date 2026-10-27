"""Minute research simulation: previous bar signal, next open fill, flat at 15:59."""
from datetime import date, timedelta
import pandas as pd

from dashboard.backtester.errors import MarketDataUnavailableError
from dashboard.backtester.intraday_data import download_minutes
from dashboard.backtester.report import summarize_backtest


def run_intraday(symbol, start, end, strategy, initial_cash, cost_bps, risk_free_rate, primary_exchange=''):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 < (last - first).days <= 31 or not 0 <= cost_bps < 10000:
        raise MarketDataUnavailableError('Use at most 31 calendar days and costs below 10000 bps.')
    frames = []
    day = first
    while day < last:
        if day.weekday() < 5:
            frame = download_minutes(symbol, day, primary_exchange)
            # Fail closed: a gap must not silently change fill timing or liquidation.
            expected = pd.date_range(f'{day} 09:30', periods=390, freq='min', tz='America/New_York').tz_convert('UTC')
            if not frame.index.equals(expected):
                raise MarketDataUnavailableError(f'{day}: this simulator requires all 390 regular-session minutes. Holidays, early closes and incomplete sessions are not supported yet; choose another range.')
            frames.append(frame)
        day += timedelta(days=1)
    if not frames:
        raise MarketDataUnavailableError('No weekday sessions in the selected range.')
    data = pd.concat(frames)
    result, ledger = simulate_minutes(data, strategy, initial_cash, cost_bps)
    daily = result.groupby(result.index.tz_convert('America/New_York').date).agg({
        'Strategy Returns': lambda s: (1 + s).prod() - 1,
        'Asset Returns': lambda s: (1 + s).prod() - 1,
        'Equity Curve': 'last', 'Positions': 'mean',
    })
    summary = summarize_backtest(daily, 252, risk_free_rate)
    summary['Time in Market'] = float(result['Positions'].mean())
    summary['Number of Market Entries'] = len(ledger)
    summary['Max Drawdown'] = float((result['Equity Curve'] / result['Equity Curve'].cummax().clip(lower=initial_cash) - 1).min())
    warnings = list(dict.fromkeys(w for frame in frames for w in frame.attrs['data_info']['warnings']))
    warnings.append('Minute simulation: signals reset each session; fills at next minute open; flat at 15:59 open. Cost applies to each buy and sell; fills are estimates, not observed quotes.')
    warnings.append('Annualized metrics use compounded session returns and 252 sessions/year; buy-and-hold includes overnight returns.')
    if len(daily) < 20:
        for key in ('Annualized Return', 'Annualized Volatility', 'Sharpe Ratio', 'Sortino Ratio'):
            summary[key] = float('nan')
        warnings.append('Fewer than 20 sessions: annualized return and risk ratios are withheld. This sample is exploratory.')
    result.attrs['data_info'] = {
        'source': 'ibkr', 'price_basis': 'Split-adjusted TRADES; dividends excluded',
        'first_date': first.isoformat(), 'last_date': frames[-1].attrs['data_info']['session'],
        'bar_count': len(data), 'fetched_at': frames[-1].attrs['data_info']['fetched_at'], 'warnings': warnings,
    }
    return result, summary, ledger


def simulate_minutes(data, strategy, initial_cash, cost_bps):
    cash, shares, previous_equity = float(initial_cash), 0.0, float(initial_cash)
    fee = cost_bps / 10000
    rows, trades = [], []
    entry = None
    previous_close = float(data['Open'].iloc[0])
    for _, session in data.groupby(data.index.tz_convert('America/New_York').date):
        signals = strategy.generate_signals(session)
        targets = signals.shift(1).fillna(0).astype(int)
        targets.iloc[-1] = 0
        for i, (stamp, bar) in enumerate(session.iterrows()):
            target = targets.iloc[i]
            price = float(bar['Open'])
            if target and not shares:
                entry = (stamp, price, cash, i)
                shares = cash / (price * (1 + fee))
                cash = 0.0
            elif not target and shares:
                cash = shares * price * (1 - fee)
                shares = 0.0
                trades.append({'Entry Date': entry[0], 'Exit Date': stamp, 'Entry Price': entry[1],
                               'Exit Price': price, 'Holding Period': i - entry[3], 'Net Return': cash / entry[2] - 1})
                entry = None
            equity = cash + shares * float(bar['Close'])
            rows.append({'Close': float(bar['Close']), 'Signals': signals.iloc[i], 'Positions': int(shares > 0),
                         'Asset Returns': float(bar['Close']) / previous_close - 1,
                         'Strategy Returns': equity / previous_equity - 1, 'Equity Curve': equity})
            previous_close, previous_equity = float(bar['Close']), equity
    return pd.DataFrame(rows, index=data.index), pd.DataFrame(trades, columns=[
        'Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Holding Period', 'Net Return'])
