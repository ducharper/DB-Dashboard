from datetime import date
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dashboard.backtester.ibkr_data import normalize_bars, download_ibkr
from dashboard.backtester.errors import MarketDataUnavailableError
import test_saved_runs


def bar(day, close=101):
    return SimpleNamespace(date=day, open=100, high=102, low=99, close=close, volume=1000)


class BarsTests(unittest.TestCase):
    def test_timeout_and_provider_error_cleanup(self):
        from ibapi.client import EClient
        original_wait = Event.wait
        for mode in ('timeout', 'error', 'empty'):
            disconnected = Event()

            def history(client, req_id, *args):
                if mode == 'error':
                    client.error(req_id, 0, 200, 'Ambiguous contract')
                elif mode == 'empty':
                    client.historicalDataEnd(req_id, '', '')

            def wait(event, timeout=None):
                return False if timeout == 45 else original_wait(event, timeout)

            with self.subTest(mode=mode), patch.object(EClient, 'connect', lambda client, *a, **kw: client.nextValidId(1)), patch.object(EClient, 'run', lambda self: disconnected.wait(5)), patch.object(EClient, 'disconnect', lambda self: disconnected.set()), patch.object(EClient, 'reqHistoricalData', history), patch.object(Event, 'wait', wait):
                with self.assertRaises(MarketDataUnavailableError):
                    download_ibkr('AAPL', '2024-01-01', '2024-02-01')
            self.assertTrue(disconnected.is_set())

    def test_sorted_deduplicated_exclusive_end(self):
        data = normalize_bars([bar('20240103'), bar('20240102'), bar('20240103'), bar('20240104')], date(2024, 1, 2), date(2024, 1, 4))
        self.assertEqual(list(data.index.strftime('%Y%m%d')), ['20240102', '20240103'])

    def test_invalid_conflicting_and_empty(self):
        for bars in ([], [bar('20240102', float('nan'))], [bar('20240102'), bar('20240102', 100)]):
            with self.subTest(bars=bars), self.assertRaises(MarketDataUnavailableError):
                normalize_bars(bars, date(2024, 1, 1), date(2024, 2, 1))

    def test_chunks_warning_and_cleanup(self):
        from ibapi.client import EClient
        disconnected = Event()
        requests = []

        def connect(client, *args, **kwargs):
            client.nextValidId(1)

        def history(client, req_id, contract, end, *args):
            requests.append(end)
            client.error(req_id, 0, 2188, 'Subscription warning')
            client.historicalData(req_id, bar('20240102'))
            client.historicalData(req_id, bar('20240103'))
            client.historicalDataEnd(req_id, '', '')

        with patch.object(EClient, 'connect', connect), patch.object(EClient, 'run', lambda self: disconnected.wait(5)), patch.object(EClient, 'disconnect', lambda self: disconnected.set()), patch.object(EClient, 'reqHistoricalData', history):
            result = download_ibkr('AAPL', '2023-01-01', '2024-02-01')
        self.assertEqual(len(requests), 2)
        self.assertTrue(disconnected.is_set())
        self.assertIn('subscription', result.attrs['data_info']['warnings'][0])


class ProviderApiTests(test_saved_runs.SavedRunsTests):
    def test_ibkr_source_and_metadata_saved(self):
        self.prices.attrs['data_info'] = dict(source='ibkr', price_basis='Split-adjusted TRADES; dividends excluded', first_date='2024-01-01', last_date='2024-07-26', bar_count=150, fetched_at='2026-10-06T00:00:00+00:00', warnings=['Delayed data'])
        with patch('dashboard.backtester.ibkr_data.download_ibkr', return_value=self.prices) as ibkr, patch('dashboard.backtester.runner.yf.download', side_effect=AssertionError('No fallback')):
            response = self.client.post('/api/backtests', json={**self.request, 'data_source': 'ibkr', 'ibkr_primary_exchange': 'NASDAQ'})
        self.assertEqual(response.status_code, 200, response.text)
        ibkr.assert_called_once_with('TEST', '2024-01-01', '2026-01-01', 'NASDAQ')
        saved = self.client.get('/api/runs/' + response.json()['run_id']).json()
        self.assertEqual(saved['request']['data_source'], 'ibkr')
        self.assertEqual(saved['result']['data_info']['warnings'], ['Delayed data'])

    def test_failure_never_falls_back_or_saves(self):
        with patch('dashboard.backtester.ibkr_data.download_ibkr', side_effect=MarketDataUnavailableError('TWS unavailable')), patch('dashboard.backtester.runner.yf.download', side_effect=AssertionError('No fallback')):
            response = self.client.post('/api/backtests', json={**self.request, 'data_source': 'ibkr'})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get('/api/runs').json(), [])

    def test_unknown_provider_rejected(self):
        self.assertEqual(self.client.post('/api/backtests', json={**self.request, 'data_source': 'other'}).status_code, 422)
