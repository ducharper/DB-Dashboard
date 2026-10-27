import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

from dashboard.backtester.engine import BackTestEngine
from dashboard.backtester.report import summarize_backtest
from dashboard.backtester.trades import build_trade_ledger
from dashboard.backtester.errors import MarketDataUnavailableError
from dashboard.strategies.base import Strategy

def run_backtest(
        symbol: str,
        start: str,
        end: str,
        strategy: Strategy,
        initial_cash: float,
        cost_bps: float,
        periods_per_year: int,
        risk_free_rate: float,
        data_source: str = 'yahoo',
        ibkr_primary_exchange: str = '',
        bar_size: str = '1 day',
) -> tuple[pd.DataFrame, dict[str, float | int], pd.DataFrame]:
    """ Reusable function that runs the backtest """

    if bar_size == '1 min':
        if data_source != 'ibkr':
            raise MarketDataUnavailableError('One-minute bars require IBKR.')
        from dashboard.backtester.intraday_engine import run_intraday
        return run_intraday(symbol, start, end, strategy, initial_cash, cost_bps, risk_free_rate, ibkr_primary_exchange)
    if data_source == 'ibkr':
        from dashboard.backtester.ibkr_data import download_ibkr
        data = download_ibkr(symbol, start, end, ibkr_primary_exchange)
    elif data_source == 'yahoo':
        data = yf.download(symbol, start=start, end=end, multi_level_index=False, auto_adjust=True)
    else:
        raise MarketDataUnavailableError('Unknown data source.')

    if data is None or data.empty:
        raise MarketDataUnavailableError(
            f"No price data was returned for {symbol} "
            f"between {start} and {end}. "
            "Check the symbol and dates, or try again later."
        )

    bt = BackTestEngine(data, strategy, initial_cash, cost_bps)
    result = bt.run()
    result.attrs['data_info'] = data.attrs.get('data_info', {
        'source': 'yahoo', 'price_basis': 'Split- and dividend-adjusted prices',
        'first_date': data.index[0].date().isoformat(), 'last_date': data.index[-1].date().isoformat(),
        'bar_count': len(data), 'fetched_at': datetime.now(timezone.utc).isoformat(), 'warnings': [],
    })
    summary = summarize_backtest(result, periods_per_year, risk_free_rate)
    ledger = build_trade_ledger(result)

    return result, summary, ledger
