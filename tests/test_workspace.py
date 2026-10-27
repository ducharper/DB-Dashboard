from contextlib import closing
import os
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from dashboard.api.main import app
from dashboard.api.workspace import database
from dashboard.backtester.errors import MarketDataUnavailableError
from dashboard.backtester.ibkr_portfolio import fetch_portfolio, number


def fixture():
    return {'source': 'ibkr', 'warnings': [], 'accounts': [{'account': 'DU_TEST', 'mode': 'paper', 'base_currency': 'USD', 'values': [{'tag': 'NetLiquidation', 'currency': 'USD', 'value': 10000}], 'positions': [{'contract_id': 123, 'symbol': 'TEST', 'security_type': 'STK', 'currency': 'USD', 'quantity': 10, 'market_price': 100, 'market_value': 1000, 'average_cost': 90, 'unrealized_pnl': 100, 'realized_pnl': 0}]}]}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'BACKTEST_DB_PATH': str(Path(self.temp.name) / 'workspace.sqlite3')})
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def refresh(self):
        with patch('dashboard.backtester.ibkr_portfolio.fetch_portfolio', return_value=fixture()):
            response = self.client.post('/api/portfolio/refresh')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_strategy_create_edit_persist_validate(self):
        response = self.client.post('/api/strategies', json={'name': 'Momentum', 'rules': 'Buy strength', 'status': 'research'})
        self.assertEqual(response.status_code, 201)
        record = response.json()
        edited = self.client.put('/api/strategies/' + record['id'], json={'name': 'Momentum', 'version': '2', 'status': 'paper'})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(TestClient(app).get('/api/strategies').json()[0]['version'], '2')
        self.assertEqual(self.client.post('/api/strategies', json={'name': ' '}).status_code, 422)
        self.assertEqual(self.client.post('/api/strategies', json={'name': 'Test', 'status': 'auto_trade'}).status_code, 422)
        self.assertEqual(self.client.put('/api/strategies/missing', json={'name': 'Test'}).status_code, 404)

    def test_refresh_notes_and_offline_reopen(self):
        self.assertIsNone(self.client.get('/api/portfolio').json()['snapshot'])
        first = self.refresh()
        strategy = self.client.post('/api/strategies', json={'name': 'Example'}).json()
        note = {'account': 'DU_TEST', 'contract_id': 123, 'thesis': 'Test thesis', 'invalidation': 'Review weekly', 'strategy_id': strategy['id']}
        self.assertEqual(self.client.put('/api/portfolio/notes', json=note).status_code, 200)
        second = self.refresh()
        self.assertNotEqual(first['snapshot']['id'], second['snapshot']['id'])
        with patch('dashboard.backtester.ibkr_portfolio.fetch_portfolio', side_effect=AssertionError('Offline read must not contact IBKR')):
            reopened = TestClient(app).get('/api/portfolio').json()
        self.assertEqual(reopened['notes'][0]['thesis'], 'Test thesis')
        self.assertEqual(reopened['notes'][0]['strategy_id'], strategy['id'])
        with closing(database()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM portfolio_snapshots').fetchone()[0], 2)

    def test_failure_preserves_previous_snapshot(self):
        first = self.refresh()
        with patch('dashboard.backtester.ibkr_portfolio.fetch_portfolio', side_effect=MarketDataUnavailableError('Offline')):
            self.assertEqual(self.client.post('/api/portfolio/refresh').status_code, 502)
        self.assertEqual(self.client.get('/api/portfolio').json(), first)

    def test_reject_unknown_position_or_strategy(self):
        self.refresh()
        self.assertEqual(self.client.put('/api/portfolio/notes', json={'account': 'DU_TEST', 'contract_id': 999}).status_code, 404)
        self.assertEqual(self.client.put('/api/portfolio/notes', json={'account': 'DU_TEST', 'contract_id': 123, 'strategy_id': 'missing'}).status_code, 422)


class AdapterTests(unittest.TestCase):
    def test_numbers(self):
        for value in [None, 'bad', float('inf'), float('nan'), 1.7976931348623157e308]:
            self.assertIsNone(number(value))
        self.assertEqual(number('-10.5'), -10.5)

    def test_readonly_snapshot_and_cleanup(self):
        self.exercise('success')

    def test_timeout_partial_and_disconnect(self):
        for mode in ['timeout', 'not_ready', 'disconnect', 'empty', 'error']:
            with self.subTest(mode=mode):
                self.exercise(mode)

    def exercise(self, mode):
        from ibapi.client import EClient
        stopped = Event()
        original_wait = Event.wait
        calls = []

        def connect(client, *args, **kwargs):
            client.managedAccounts('DU_TEST')
            client.nextValidId(1)

        def updates(client, subscribe, account):
            calls.append((subscribe, account))
            if not subscribe:
                return
            if mode == 'timeout':
                return
            if mode == 'disconnect':
                client.connectionClosed(); return
            if mode == 'error':
                client.error(-1, 0, 2101, 'Other account subscription'); return
            if mode != 'empty':
                client.updateAccountValue('NetLiquidation', '10000', 'USD', account)
                client.updateAccountValue('Currency', 'USD', '', account)
                contract = SimpleNamespace(conId=123, localSymbol='TEST', symbol='TEST', currency='USD', secType='STK')
                client.updatePortfolio(contract, 10, 100, 1000, 90, 100, 0, account)
            if mode == 'not_ready':
                client.updateAccountValue('accountReady', 'false', '', account)
            client.accountDownloadEnd(account)

        with patch.object(EClient, 'connect', connect), patch.object(EClient, 'run', lambda self: stopped.wait(5)), patch.object(EClient, 'disconnect', lambda self: stopped.set()), patch.object(EClient, 'reqAccountUpdates', updates), patch.object(EClient, 'placeOrder', side_effect=AssertionError('Never place orders')), patch.object(Event, 'wait', lambda self, timeout=None: self.is_set() if timeout == 15 else original_wait(self, timeout)):
            if mode == 'success':
                # Completion is synchronous in this fake; preserve that event result.
                with patch.object(Event, 'wait', lambda self, timeout=None: self.is_set() if timeout == 15 else original_wait(self, timeout)):
                    result = fetch_portfolio()
                self.assertEqual(result['accounts'][0]['positions'][0]['contract_id'], 123)
                self.assertEqual(result['accounts'][0]['mode'], 'paper')
                self.assertIn((False, 'DU_TEST'), calls)
            else:
                with self.assertRaises(MarketDataUnavailableError):
                    fetch_portfolio()
        self.assertTrue(stopped.is_set())
