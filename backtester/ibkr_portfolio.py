"""One-shot account snapshots. No order, execution or account-changing calls."""
from math import isfinite
from threading import Event, Lock, Thread
from backtester.errors import MarketDataUnavailableError

_lock = Lock()


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) and abs(result) < 1e100 else None
    except (ValueError, TypeError):
        return None


def fetch_portfolio():
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
    except ImportError as exc:
        raise MarketDataUnavailableError('Install the official IBKR Python API; see START_HERE.md.') from exc
    if not _lock.acquire(blocking=False):
        raise MarketDataUnavailableError('A portfolio refresh is already running. Please wait.')

    class Snapshot(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.ready, self.accounts_ready, self.done = Event(), Event(), Event()
            self.accounts, self.records = [], {}
            self.failure, self.active = None, None
            self.warnings = []

        def nextValidId(self, orderId):
            self.ready.set()

        def managedAccounts(self, accountsList):
            self.accounts = [a for a in accountsList.split(',') if a]
            self.accounts_ready.set()

        def updateAccountValue(self, key, val, currency, accountName):
            if accountName != self.active:
                return
            record = self.records[accountName]
            if key == 'accountReady' and val.lower() == 'false':
                self.failure = 'IBKR account values are not ready. Try again after TWS finishes loading.'
                self.done.set()
            if key == 'Currency':
                record['base_currency'] = val
            if key in {'NetLiquidation', 'TotalCashValue', 'UnrealizedPnL', 'RealizedPnL', 'BuyingPower', 'MaintMarginReq', 'AvailableFunds'}:
                record['values'][key + ':' + currency] = {'tag': key, 'currency': currency, 'value': number(val)}

        def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName):
            if accountName != self.active:
                return
            if contract.conId <= 0 or number(position) is None:
                self.failure = 'IBKR returned an invalid position identifier or quantity.'
                self.done.set()
                return
            self.records[accountName]['positions'][contract.conId] = {
                'contract_id': contract.conId, 'symbol': contract.localSymbol or contract.symbol,
                'security_type': contract.secType, 'currency': contract.currency,
                'quantity': number(position), 'market_price': number(marketPrice),
                'market_value': number(marketValue), 'average_cost': number(averageCost),
                'unrealized_pnl': number(unrealizedPNL), 'realized_pnl': number(realizedPNL),
            }

        def accountDownloadEnd(self, accountName):
            if accountName == self.active:
                self.done.set()

        def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=''):
            if errorCode in {2104, 2106, 2107, 2108, 2158}:
                return
            # 2100/2101 indicate competing account subscriptions: never accept partial data.
            self.failure = (f'IBKR portfolio request failed (code {errorCode}). Open and log into paper TWS on port 7497; enable socket clients and keep Read-Only API enabled.' if errorCode in {502, 504, 1100, 1300} else f'IBKR portfolio request failed (code {errorCode}). Check account permissions or competing account-data subscriptions in TWS.')
            self.ready.set(); self.accounts_ready.set(); self.done.set()

        def connectionClosed(self):
            self.failure = self.failure or 'TWS disconnected during the refresh. The previous snapshot is unchanged.'
            self.ready.set(); self.accounts_ready.set(); self.done.set()

    app, stop = Snapshot(), Event()

    def worker():
        try:
            app.connect('127.0.0.1', 7497, clientId=51)
            if not stop.is_set():
                app.run()
        except Exception:
            app.failure = 'Could not connect to paper TWS on localhost:7497. Log in and enable socket clients; keep Read-Only API enabled.'
            app.ready.set(); app.accounts_ready.set(); app.done.set()
        finally:
            app.disconnect()
            _lock.release()

    thread = Thread(target=worker, daemon=True)
    thread.start()
    try:
        if not app.ready.wait(12) or not app.accounts_ready.wait(5) or app.failure:
            raise MarketDataUnavailableError(app.failure or 'TWS did not respond. Open paper TWS on port 7497 and try again.')
        if not app.accounts or len(app.accounts) > 10:
            raise MarketDataUnavailableError('This version supports sessions with 1–10 accounts.')
        for account in app.accounts:
            app.active = account
            app.records[account] = {'account': account, 'mode': 'paper' if account.startswith('DU') else 'live_or_unverified', 'base_currency': None, 'values': {}, 'positions': {}}
            app.done.clear()
            app.reqAccountUpdates(True, account)
            if not app.done.wait(15) or app.failure:
                raise MarketDataUnavailableError(app.failure or 'Account download timed out. No partial snapshot was saved.')
            app.reqAccountUpdates(False, account)
            app.active = None
            record = app.records[account]
            if not record['values']:
                raise MarketDataUnavailableError('IBKR returned no account values. No partial snapshot was saved.')
        if app.failure:
            raise MarketDataUnavailableError(app.failure)
        accounts = [{**record, 'values': list(record['values'].values()), 'positions': [p for p in record['positions'].values() if p['quantity'] != 0]} for record in app.records.values()]
        return {'accounts': accounts, 'source': 'ibkr', 'warnings': ['On-demand TWS snapshot, not a streaming quote feed. Prices may be delayed; verify in TWS before making decisions.', 'P&L fields are reported by TWS, not calculated period returns. No deposits/withdrawals adjustment or strategy attribution is implied.']}
    finally:
        stop.set()
        if app.isConnected() and app.active:
            app.reqAccountUpdates(False, app.active)
        app.disconnect()
        thread.join(3)
