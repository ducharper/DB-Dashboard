r"""One-shot TWS connectivity check. Requests server time only; never sends orders.

Run with .venv\Scripts\python.exe -m dashboard.cli.check_ibkr while paper TWS is open.
Requires the official IBKR Python API installed from IBKR's downloaded SDK.
"""
import threading
from datetime import datetime, timezone

from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class ConnectionCheck(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.received_time = threading.Event()
        self.timestamp = None

    def nextValidId(self, orderId):
        # TWS sends this automatically as its handshake completes; no order is sent.
        self.ready.set()

    def currentTime(self, time):
        self.timestamp = time
        self.received_time.set()

    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=''):
        if errorCode not in {2104, 2106, 2107, 2108, 2158}:
            print(f'TWS message {errorCode}: {errorString}')

    def managedAccounts(self, accountsList):
        # The handshake sends account identifiers; do not print or store them.
        pass


def main():
    app = ConnectionCheck()
    worker = None
    try:
        app.connect('127.0.0.1', 7497, clientId=47)
        worker = threading.Thread(target=app.run, daemon=True)
        worker.start()
        if not app.ready.wait(10):
            raise RuntimeError('TWS handshake timed out. Check API settings and any connection-approval prompt in TWS.')
        app.reqCurrentTime()
        if not app.received_time.wait(10):
            raise RuntimeError('Connected, but TWS did not return its server time.')
        print('PASS: TWS handshake and server-time request succeeded on 127.0.0.1:7497.')
        print('Server time (UTC):', datetime.fromtimestamp(app.timestamp, timezone.utc).isoformat())
        print('No orders, positions, or balances were requested. This does not test market-data permissions.')
    finally:
        app.disconnect()
        if worker:
            worker.join(timeout=3)


if __name__ == '__main__':
    main()
