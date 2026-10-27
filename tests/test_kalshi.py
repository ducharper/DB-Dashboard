import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from dashboard.api.main import app
from dashboard.api.kalshi import SizingRequest, size_trade

class KalshiTests(unittest.TestCase):
    def settings(self, **changes):
        values = dict(probability=.65, uncertainty=.05, price=.5, cost_allowance=.02,
                      bankroll=1000, available_cash=1000, existing_event_risk=0,
                      kelly_fraction=.25, trade_cap=.01, event_cap=.03)
        values.update(changes)
        return SizingRequest(**values)

    def test_caps_and_payoffs(self):
        result = size_trade(self.settings())
        self.assertEqual(result['contracts'], 19)
        self.assertLessEqual(result['max_loss'], 10)
        self.assertAlmostEqual(result['expected_profit'], 19 * .13)
        self.assertAlmostEqual(result['loss_probability'], .35)
        self.assertAlmostEqual(result['profit_if_win'], 19 * .48)

    def test_no_edge_and_exhausted_limits(self):
        for changes in [dict(probability=.55), dict(existing_event_risk=30), dict(available_cash=.1)]:
            self.assertEqual(size_trade(self.settings(**changes))['contracts'], 0)

    def test_kelly_binding_and_event_headroom(self):
        result = size_trade(self.settings(trade_cap=1, event_cap=1))
        self.assertEqual(result['contracts'], int((1000 * .25 * (.6-.52)/.48)/.52))
        self.assertLessEqual(size_trade(self.settings(existing_event_risk=29))['max_loss'], 1)

    def test_validation(self):
        client = TestClient(app)
        data = self.settings().model_dump()
        for key, value in [('probability', 1.1), ('bankroll', -1), ('price', 0)]:
            self.assertEqual(client.post('/api/kalshi/size', json={**data, key: value}).status_code, 422)
        self.assertEqual(client.post('/api/kalshi/size', json={**data, 'cost_allowance': .6}).status_code, 422)

    @patch('dashboard.api.kalshi.fetch_public')
    def test_quotes_pagination_and_missing_values(self, fetch):
        fetch.return_value = {'markets': [{'ticker': 'TEST', 'market_type': 'binary', 'yes_ask_dollars': '0.5500', 'no_ask_dollars': '0', 'yes_bid_dollars': 'NaN'}], 'cursor': 'next'}
        response = TestClient(app).get('/api/kalshi/markets?series=KXNFLGAME&cursor=abc')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['markets'][0]['yes_ask'], .55)
        self.assertIsNone(data['markets'][0]['no_ask'])
        self.assertIsNone(data['markets'][0]['yes_bid'])
        self.assertEqual(data['cursor'], 'next')
        self.assertEqual(fetch.call_args.args[0]['cursor'], 'abc')

    @patch('dashboard.api.kalshi.urlopen', side_effect=TimeoutError)
    def test_provider_failure(self, fetch):
        self.assertEqual(TestClient(app).get('/kalshi/markets').status_code, 502)
