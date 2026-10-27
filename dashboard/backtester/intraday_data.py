"""Read-only, single-session IBKR minute history for research, not trade execution."""
from datetime import date, datetime, time, timedelta, timezone
import math
from threading import Event, Thread

import pandas as pd

from dashboard.backtester.errors import MarketDataUnavailableError
from dashboard.backtester.ibkr_data import _connection_lock


def normalize_minutes(bars, session: date) -> pd.DataFrame:
    """IBKR formatDate=2 gives epoch seconds marking the START of each bar."""
    rows = {}
    for bar in bars:
        try:
            stamp = pd.Timestamp(int(bar.date), unit='s', tz='UTC')
            local = stamp.tz_convert('America/New_York')
            values = tuple(float(getattr(bar, name)) for name in ('open', 'high', 'low', 'close', 'volume'))
            o, h, low, c, v = values
            if (not all(math.isfinite(x) for x in values) or min(o, h, low, c) <= 0
                    or v < 0 or not low <= min(o, c) <= max(o, c) <= h or stamp.second != 0):
                raise ValueError('Invalid minute bar')
            if stamp in rows and rows[stamp] != values:
                raise ValueError('Conflicting duplicate minute')
            # The UTC request window can include other local dates. Keep only RTH.
            if local.date() == session and time(9, 30) <= local.time() < time(16):
                rows[stamp] = values
        except (ValueError, TypeError, AttributeError, OverflowError) as exc:
            raise MarketDataUnavailableError('IBKR returned invalid or conflicting minute bars.') from exc
    if len(rows) < 2:
        raise MarketDataUnavailableError('Fewer than two regular-session minute bars returned. Check the trading date and data permissions.')
    stamps = sorted(rows)
    frame = pd.DataFrame([rows[s] for s in stamps], index=pd.DatetimeIndex(stamps, name='timestamp_utc'),
                         columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    local = frame.index.tz_convert('America/New_York')
    warnings = ['Research bars only: no bid/ask quotes or auction-imbalance messages. Missing minutes are not filled.']
    if len(frame) != 390 or local[0].time() != time(9, 30) or local[-1].time() != time(15, 59):
        warnings.append('Coverage differs from a normal 390-minute session. Check holidays, early closes, halts, or missing data before analysis.')
    frame.attrs['data_info'] = {
        'source': 'ibkr', 'bar_size': '1 min', 'session': session.isoformat(),
        'timestamp_convention': 'Bar start, UTC; local timezone America/New_York',
        'regular_hours_only': True, 'price_basis': 'Split-adjusted TRADES; dividends excluded',
        'first_timestamp': stamps[0].isoformat(), 'last_timestamp': stamps[-1].isoformat(),
        'bar_count': len(frame), 'fetched_at': datetime.now(timezone.utc).isoformat(), 'warnings': warnings,
    }
    return frame


def download_minutes(symbol: str, session: date, primary_exchange: str = '') -> pd.DataFrame:
    """Download one completed US stock/ETF session through paper TWS (7497)."""
    if not symbol.strip():
        raise MarketDataUnavailableError('A stock or ETF symbol is required.')
    if session >= pd.Timestamp.now(tz='America/New_York').date() or session.weekday() >= 5:
        raise MarketDataUnavailableError('Choose a completed weekday session before today; exchange holidays may have no data.')
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
    except ImportError as exc:
        raise MarketDataUnavailableError('Install the official IBKR Python API as described in START_HERE.md.') from exc

    if not _connection_lock.acquire(blocking=False):
        raise MarketDataUnavailableError('Another IBKR download is running. Wait for it to finish.')

    class History(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.ready, self.done = Event(), Event()
            self.bars, self.warnings = [], []
            self.failure = None

        def managedAccounts(self, accountsList):
            pass

        def nextValidId(self, orderId):
            self.ready.set()

        def historicalData(self, reqId, bar):
            if reqId == 1:
                self.bars.append(bar)

        def historicalDataEnd(self, reqId, start, end):
            if reqId == 1:
                self.done.set()

        def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=''):
            if errorCode in {2104, 2106, 2107, 2108, 2158}:
                return
            if errorCode == 2188:
                self.warnings.append('IBKR reports that up-to-the-second data requires an additional subscription; historical data may be delayed.')
                return
            if reqId == 1 or errorCode in {502, 504, 1100, 1300, 326}:
                self.failure = f'IBKR {errorCode}: {errorString}'
                self.ready.set()
                self.done.set()

        def connectionClosed(self):
            if not self.done.is_set():
                self.failure = self.failure or 'TWS disconnected before history completed.'
                self.ready.set()
                self.done.set()

    app = History()
    worker = None
    requested = False
    try:
        app.connect('127.0.0.1', 7497, clientId=50)
        worker = Thread(target=app.run, daemon=True)
        worker.start()
        if not app.ready.wait(12) or app.failure:
            raise MarketDataUnavailableError(app.failure or 'Open paper TWS, enable socket clients on port 7497, and keep Read-Only API enabled.')
        contract = Contract()
        contract.symbol = symbol.strip().upper()
        contract.secType, contract.exchange, contract.currency = 'STK', 'SMART', 'USD'
        contract.primaryExchange = primary_exchange.strip().upper()
        end = datetime.combine(session + timedelta(days=1), time(), timezone.utc)
        requested = True
        app.reqHistoricalData(1, contract, end.strftime('%Y%m%d-%H:%M:%S'), '1 D', '1 min', 'TRADES', 1, 2, False, [])
        if not app.done.wait(45):
            raise MarketDataUnavailableError('Minute history timed out; partial bars were discarded.')
        if app.failure:
            raise MarketDataUnavailableError(app.failure)
        frame = normalize_minutes(app.bars, session)
        frame.attrs['data_info'].update(symbol=contract.symbol, primary_exchange=contract.primaryExchange)
        frame.attrs['data_info']['warnings'].extend(app.warnings)
        return frame
    finally:
        if requested and not app.done.is_set() and app.isConnected():
            app.cancelHistoricalData(1)
        app.disconnect()
        if worker:
            worker.join(timeout=3)
        _connection_lock.release()
