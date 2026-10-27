import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from dashboard.api.main import app
from dashboard.api import history


class SavedRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'BACKTEST_DB_PATH': str(Path(self.temp.name) / 'runs.sqlite3')})
        self.env.start()
        self.client = TestClient(app)
        self.request = {'symbol': 'TEST', 'start': '2024-01-01', 'end': '2026-01-01', 'strategy': {'name': 'moving_average', 'short_window': 5, 'long_window': 20}}
        self.prices = pd.DataFrame({'Close': 100 + np.arange(150) * .05 + 10 * np.sin(np.arange(150) / 5)}, index=pd.bdate_range('2024-01-01', periods=150))

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def run_backtest(self):
        with patch('dashboard.backtester.runner.yf.download', return_value=self.prices):
            response = self.client.post('/api/backtests', json=self.request)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_save_reopen_and_soft_delete(self):
        result = self.run_backtest()
        run_id = result['run_id']
        # New client and new database connections: no in-memory persistence dependency.
        with TestClient(app) as restarted, patch('dashboard.backtester.runner.yf.download', side_effect=AssertionError('Reopening must not download')):
            listing = restarted.get('/api/runs').json()
            self.assertEqual(listing[0]['id'], run_id)
            saved = restarted.get('/api/runs/' + run_id).json()
            self.assertEqual(saved['result']['equity'], result['equity'])
            self.assertEqual(saved['result']['trades'], result['trades'])
            self.assertEqual(saved['request']['initial_cash'], 10000)
            self.assertEqual(restarted.delete('/api/runs/' + run_id).status_code, 204)
            self.assertEqual(restarted.get('/api/runs').json(), [])
            self.assertEqual(restarted.get('/api/runs/' + run_id).status_code, 404)
            self.assertEqual(restarted.delete('/api/runs/' + run_id).status_code, 404)
        with closing(sqlite3.connect(history.database_path())) as db:
            self.assertEqual(db.execute('SELECT deleted FROM runs WHERE id=?', (run_id,)).fetchone()[0], 1)

    def test_failed_requests_are_not_saved(self):
        with patch('dashboard.backtester.runner.yf.download', return_value=pd.DataFrame()):
            self.assertEqual(self.client.post('/api/backtests', json=self.request).status_code, 502)
        self.assertEqual(self.client.post('/api/backtests', json={**self.request, 'initial_cash': -1}).status_code, 422)
        self.assertEqual(self.client.get('/api/runs').json(), [])

    def test_pagination_and_legacy_routes(self):
        self.run_backtest()
        self.run_backtest()
        first = self.client.get('/runs?limit=1').json()
        second = self.client.get('/runs?limit=1&offset=1').json()
        self.assertNotEqual(first[0]['id'], second[0]['id'])
        self.assertEqual(self.client.get('/runs?offset=-1').status_code, 422)
        self.assertEqual(self.client.get('/runs?limit=101').status_code, 422)

    def test_storage_failure_is_explicit(self):
        with patch('dashboard.backtester.runner.yf.download', return_value=self.prices), patch('dashboard.api.history.save_run', side_effect=sqlite3.OperationalError('disk full')):
            response = self.client.post('/api/backtests', json=self.request)
        self.assertEqual(response.status_code, 503)
        self.assertIn('could not be saved', response.json()['detail'])

    def test_local_app_serves_built_website_and_health(self):
        self.assertEqual(self.client.get('/health').json()['app'], 'practice-backtester')
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIn('Practice Backtester', self.client.get('/').text)


if __name__ == '__main__':
    unittest.main()
