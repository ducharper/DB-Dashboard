from datetime import date
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import test_saved_runs
from dashboard.backtester.intraday_data import normalize_minutes
from dashboard.backtester.intraday_engine import simulate_minutes, run_intraday
from dashboard.backtester.errors import MarketDataUnavailableError


class Signals:
    def generate_signals(self, data):
        return pd.Series([1] * len(data), index=data.index)


class ExecutionTests(unittest.TestCase):
    def test_next_open_costs_and_no_overnight_position(self):
        index = pd.date_range('2024-07-08 13:30', periods=4, freq='min', tz='UTC')
        frame = pd.DataFrame({'Open': [10, 20, 30, 40], 'Close': [19, 29, 39, 100]}, index=index)
        second = frame.copy()
        second.index += pd.Timedelta(days=1)
        result, ledger = simulate_minutes(pd.concat([frame, second]), Signals(), 1000, 100)
        trade_factor = 40 / 20 * .99 / 1.01
        self.assertAlmostEqual(result['Equity Curve'].iloc[-1], 1000 * trade_factor ** 2)
        self.assertEqual(list(ledger['Entry Price']), [20, 20])
        self.assertEqual(list(ledger['Exit Price']), [40, 40])
        self.assertEqual(list(result['Positions']), [0, 1, 1, 0] * 2)
        self.assertAlmostEqual(ledger['Net Return'].iloc[0], trade_factor - 1)
        self.assertEqual(ledger['Holding Period'].iloc[0], 2)


class IntradayApiTests(test_saved_runs.SavedRunsTests):
    def minute_frame(self):
        from types import SimpleNamespace
        index = pd.date_range('2024-07-08 13:30', periods=390, freq='min', tz='UTC')
        bars = [SimpleNamespace(date=str(int(t.timestamp())), open=100 + i / 100,
                                high=106, low=99, close=100.1 + i / 100, volume=1000)
                for i, t in enumerate(index)]
        return normalize_minutes(bars, date(2024, 7, 8))

    def test_minute_save_reopen_and_daily_annualization(self):
        request = {**self.request, 'start': '2024-07-08', 'end': '2024-07-09',
                   'data_source': 'ibkr', 'bar_size': '1 min', 'periods_per_year': 98280}
        with patch('dashboard.backtester.intraday_engine.download_minutes', return_value=self.minute_frame()):
            response = self.client.post('/api/backtests', json=request)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(len(result['equity']), 390)
        self.assertEqual(result['equity'][0]['date'], '2024-07-08T09:30:00-04:00')
        self.assertTrue(result['trades'][0]['exit_date'].endswith('15:59:00-04:00'))
        self.assertIsNone(result['summary']['Sharpe Ratio'])
        saved = self.client.get('/api/runs/' + result['run_id']).json()
        self.assertEqual(saved['request']['periods_per_year'], 252)
        self.assertEqual(saved['result']['equity'], result['equity'])

    def test_reject_incomplete_session_and_invalid_provider(self):
        with patch('dashboard.backtester.intraday_engine.download_minutes', return_value=self.minute_frame().iloc[:-1]):
            with self.assertRaises(MarketDataUnavailableError):
                run_intraday('AAPL', '2024-07-08', '2024-07-09', Signals(), 1000, 5, .04)
        response = self.client.post('/api/backtests', json={**self.request, 'bar_size': '1 min'})
        self.assertEqual(response.status_code, 422)
