"""Read-only daily US-stock history from the local TWS paper API.

No order methods are called. Failure never switches providers silently.
"""
from datetime import date, datetime, timedelta, timezone
from threading import Event, Lock, Thread
import math

import pandas as pd

from dashboard.backtester.errors import MarketDataUnavailableError

_connection_lock = Lock()


def normalize_bars(bars, start: date, end: date) -> pd.DataFrame:
    rows = {}
    for bar in bars:
        try:
            day = datetime.strptime(bar.date, '%Y%m%d').date()
            values = tuple(float(getattr(bar, name)) for name in ('open', 'high', 'low', 'close', 'volume'))
            o, h, low, c, v = values
            if not all(math.isfinite(x) for x in values) or min(o, h, low, c) <= 0 or v < 0 or not low <= min(o, c) <= max(o, c) <= h:
                raise ValueError('Invalid OHLCV')
            if day in rows and rows[day] != values:
                raise ValueError('Conflicting duplicate bars')
            rows[day] = values
        except (ValueError, TypeError, AttributeError) as exc:
            raise MarketDataUnavailableError('IBKR returned invalid or conflicting daily prices; no backtest was run.') from exc
    selected = sorted(day for day in rows if start <= day < end)
    if len(selected) < 2:
        raise MarketDataUnavailableError('IBKR returned fewer than two daily bars. Check dates, symbol, and historical-data permissions.')
    return pd.DataFrame([rows[d] for d in selected], index=pd.DatetimeIndex(selected), columns=['Open', 'High', 'Low', 'Close', 'Volume'])


def download_ibkr(symbol: str, start: str, end: str, primary_exchange: str = '') -> pd.DataFrame:
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
    except ImportError as exc:
        raise MarketDataUnavailableError('IBKR Python API is not installed. See START_HERE.md for the official TWS API installation.') from exc

    first, last = date.fromisoformat(start), date.fromisoformat(end)
    # Midnight UTC precedes the US session: never include an unfinished daily bar.
    last = min(last, datetime.now(timezone.utc).date())
    if first >= last or (last - first).days > 365 * 20:
        raise MarketDataUnavailableError('For IBKR, choose a past start date and a range no longer than 20 years.')
    if not _connection_lock.acquire(blocking=False):
        raise MarketDataUnavailableError('Another IBKR download is running. Wait for it to finish before trying again.')

    class History(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.ready, self.done = Event(), Event()
            self.bars, self.warnings = [], []
            self.failure = None
            self.request_id = 0

        def nextValidId(self, orderId):
            self.ready.set()

        def managedAccounts(self, accountsList):
            pass  # Account identifiers are irrelevant to historical data.

        def historicalData(self, reqId, bar):
            if reqId == self.request_id:
                self.bars.append(bar)

        def historicalDataEnd(self, reqId, start, end):
            if reqId == self.request_id:
                self.done.set()

        def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=''):
            if errorCode in {2104, 2106, 2107, 2108, 2158}:
                return
            if errorCode == 2188:
                warning = 'IBKR: up-to-the-second historical data requires an additional subscription; returned history may be delayed.'
                if warning not in self.warnings:
                    self.warnings.append(warning)
                return
            if reqId == self.request_id or errorCode in {502, 504, 1100, 1300, 326}:
                self.failure = f'IBKR error {errorCode}: {errorString}. Check TWS, market-data permissions, and the symbol/primary exchange.'
                self.ready.set()
                self.done.set()

        def connectionClosed(self):
            self.failure = self.failure or 'TWS disconnected before the historical download finished.'
            self.ready.set()
            self.done.set()

    app = History()
    stopped = Event()

    def worker():
        try:
            app.connect('127.0.0.1', 7497, clientId=49)
            if not stopped.is_set():
                app.run()
        except Exception as exc:
            app.failure = f'Could not connect to TWS: {exc}'
            app.ready.set()
            app.done.set()
        finally:
            app.disconnect()
            _connection_lock.release()

    thread = Thread(target=worker, daemon=True)
    thread.start()
    try:
        if not app.ready.wait(12) or app.failure:
            raise MarketDataUnavailableError(app.failure or 'TWS did not respond. Open and log into paper TWS, enable socket clients on port 7497, and keep Read-Only API enabled.')
        contract = Contract()
        contract.symbol = symbol.strip().upper()
        contract.secType, contract.exchange, contract.currency = 'STK', 'SMART', 'USD'
        contract.primaryExchange = primary_exchange.strip().upper()
        cursor = last
        while cursor > first:
            count_before = len(app.bars)
            app.request_id += 1
            app.done.clear()
            app.reqHistoricalData(app.request_id, contract, cursor.strftime('%Y%m%d') + '-00:00:00', '1 Y', '1 day', 'TRADES', 1, 1, False, [])
            if not app.done.wait(45):
                raise MarketDataUnavailableError('IBKR historical download timed out. No partial result was used. Check TWS and retry with a shorter date range.')
            if app.failure:
                raise MarketDataUnavailableError(app.failure)
            if len(app.bars) == count_before:
                raise MarketDataUnavailableError('IBKR returned an empty historical segment. No partial backtest was run; choose a shorter date range.')
            cursor -= timedelta(days=364)  # Overlap prevents gaps across leap years.
        data = normalize_bars(app.bars, first, last)
        warnings = list(app.warnings)
        if date.fromisoformat(end) > last:
            warnings.append('Only completed daily sessions were requested; today and future dates were excluded.')
        if (data.index[0].date() - first).days > 7 or (last - data.index[-1].date()).days > 7 or data.index.to_series().diff().dt.days.gt(7).any():
            warnings.append('Returned history has a boundary shortfall or a gap longer than seven calendar days. Check coverage before interpreting performance.')
        data.attrs['data_info'] = {
            'source': 'ibkr', 'price_basis': 'Split-adjusted TRADES; dividends excluded',
            'first_date': data.index[0].date().isoformat(), 'last_date': data.index[-1].date().isoformat(),
            'bar_count': len(data), 'fetched_at': datetime.now(timezone.utc).isoformat(),
            'warnings': warnings,
        }
        return data
    finally:
        stopped.set()
        if app.isConnected() and app.request_id and not app.done.is_set():
            app.cancelHistoricalData(app.request_id)
        app.disconnect()
        thread.join(timeout=3)
