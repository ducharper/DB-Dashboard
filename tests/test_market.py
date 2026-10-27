import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from dashboard.api import market
from dashboard.api.main import app


class MarketSnapshotTests(unittest.TestCase):
    def setUp(self):
        market._cached = None
        market._expires = 0

    def tearDown(self):
        market._cached = None
        market._expires = 0

    @patch('dashboard.api.market.yf.download')
    def test_prices_dates_changes_and_cache(self, download):
        download.return_value = pd.DataFrame({'Close': [100, float('nan'), 105]},
                                            index=pd.date_range('2026-09-01', periods=3))
        client = TestClient(app)
        response = client.get('/api/market-snapshot')
        self.assertEqual(response.status_code, 200)
        quote = response.json()['items'][0]
        self.assertEqual(quote['price'], 105)
        self.assertAlmostEqual(quote['change'], .05)
        self.assertEqual(quote['date'], '2026-09-03')
        self.assertEqual(len(quote['points']), 2)
        self.assertEqual(client.get('/market-snapshot').json(), response.json())
        self.assertEqual(download.call_count, 3)

    @patch('dashboard.api.market.yf.download')
    def test_provider_failure_is_explicit_and_other_symbols_survive(self, download):
        frame = pd.DataFrame({'Close': [100, 99]}, index=pd.date_range('2026-09-01', periods=2))
        download.side_effect = [RuntimeError('offline'), frame, frame]
        items = market.market_snapshot()['items']
        self.assertIsNone(items[0]['price'])
        self.assertEqual(items[0]['points'], [])
        self.assertEqual(items[1]['price'], 99)
        self.assertAlmostEqual(items[1]['change'], -.01)
