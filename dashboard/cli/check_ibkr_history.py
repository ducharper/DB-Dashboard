"""Read-only AAPL daily-price probe; does not alter the backtester or saved runs."""
import math
import threading
from datetime import datetime, timedelta, timezone

from ibapi.contract import Contract
from dashboard.cli.check_ibkr import ConnectionCheck


class HistoryCheck(ConnectionCheck):
    request_id = 101

    def __init__(self):
        super().__init__()
        self.finished = threading.Event()
        self.bars = []
        self.failure = None

    def historicalData(self, reqId, bar):
        if reqId == self.request_id:
            self.bars.append(bar)

    def historicalDataEnd(self, reqId, start, end):
        if reqId == self.request_id:
            self.finished.set()

    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=''):
        super().error(reqId, errorTime, errorCode, errorString, advancedOrderRejectJson)
        if errorCode == 2188:
            # Retain the notice above, but wait for bars/completion: this can
            # accompany a response missing only the up-to-the-second tail.
            return
        if reqId == self.request_id or errorCode in {502, 504, 1100, 1300}:
            self.failure = f'IBKR {errorCode}: {errorString}'
            self.finished.set()


def validate(bars, end):
    if not bars:
        raise RuntimeError('TWS completed the request but returned no prices.')
    dates = [datetime.strptime(bar.date, '%Y%m%d').date() for bar in bars]
    if dates != sorted(set(dates)):
        raise RuntimeError('Dates are duplicated or not in ascending order.')
    if dates[0] < end - timedelta(days=35) or dates[-1] >= end:
        raise RuntimeError('Returned dates are outside the expected completed-day window.')
    for bar in bars:
        prices = [bar.open, bar.high, bar.low, bar.close]
        if not all(math.isfinite(value) and value > 0 for value in prices):
            raise RuntimeError(f'Invalid price on {bar.date}.')
        if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
            raise RuntimeError(f'Inconsistent OHLC prices on {bar.date}.')
        if not math.isfinite(float(bar.volume)) or bar.volume < 0:
            raise RuntimeError(f'Invalid volume on {bar.date}.')
    return dates


def main():
    app = HistoryCheck()
    end = datetime.now(timezone.utc).date()
    worker = None
    requested = False
    try:
        app.connect('127.0.0.1', 7497, clientId=48)
        worker = threading.Thread(target=app.run, daemon=True)
        worker.start()
        if not app.ready.wait(10):
            raise RuntimeError(app.failure or 'TWS handshake timed out. Check that paper TWS is logged in and API connections are enabled.')
        contract = Contract()
        contract.symbol = 'AAPL'
        contract.secType = 'STK'
        contract.exchange = 'SMART'
        contract.primaryExchange = 'NASDAQ'
        contract.currency = 'USD'
        print(f'Requesting AAPL: 1 M ending {end} 00:00 UTC; daily TRADES, regular trading hours only.', flush=True)
        requested = True
        app.reqHistoricalData(app.request_id, contract, end.strftime('%Y%m%d') + '-00:00:00', '1 M', '1 day', 'TRADES', 1, 1, False, [])
        if not app.finished.wait(45):
            raise RuntimeError('Historical request timed out; partial data is not treated as success.')
        if app.failure:
            raise RuntimeError(app.failure)
        dates = validate(app.bars, end)
        print(f'PASS: {len(dates)} daily bars, {dates[0]} through {dates[-1]}.')
        print('Checks passed: nonempty response, unique chronological dates, positive finite prices, consistent OHLC, nonnegative volume.')
        for bar in app.bars[-3:]:
            print(f'{bar.date}: open={bar.open:.2f}, high={bar.high:.2f}, low={bar.low:.2f}, close={bar.close:.2f}')
        print('TRADES prices are split-adjusted, not dividend-adjusted. No orders were sent; no runs were saved.')
    finally:
        if requested and not app.finished.is_set() and app.isConnected():
            app.cancelHistoricalData(app.request_id)
        app.disconnect()
        if worker:
            worker.join(timeout=3)


if __name__ == '__main__':
    main()
