from datetime import date
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from backtester.errors import MarketDataUnavailableError
from backtester.intraday_data import download_minutes, normalize_minutes


def bar(stamp, close=101):
    return SimpleNamespace(date=str(int(pd.Timestamp(stamp).timestamp())), open=100, high=102,
                           low=99, close=close, volume=1000)


class MinuteTests(unittest.TestCase):
    def test_dst_session_boundaries_and_duplicates(self):
        for session, opening in [(date(2026, 1, 5), '2026-01-05T14:30:00Z'),
                                 (date(2026, 7, 6), '2026-07-06T13:30:00Z')]:
            start = pd.Timestamp(opening)
            bars = [bar(start + pd.Timedelta(minutes=i)) for i in range(-1, 391)]
            frame = normalize_minutes(list(reversed(bars)) + [bars[1]], session)
            self.assertEqual(len(frame), 390)
            self.assertTrue(frame.index.is_monotonic_increasing)
            self.assertEqual(frame.index[0].tz_convert('America/New_York').hour, 9)
            self.assertEqual(len(frame.attrs['data_info']['warnings']), 1)

    def test_invalid_conflicting_and_missing_data(self):
        first = bar('2026-07-06T13:30:00Z')
        second = bar('2026-07-06T13:32:00Z')
        for bars in ([], [first], [first, bar('2026-07-06T13:30:00Z', 100)],
                     [first, bar('2026-07-06T13:31:00Z', float('nan'))]):
            with self.subTest(bars=bars), self.assertRaises(MarketDataUnavailableError):
                normalize_minutes(bars, date(2026, 7, 6))
        result = normalize_minutes([first, second], date(2026, 7, 6))
        self.assertEqual(len(result), 2)  # Never manufacture a missing minute.
        self.assertEqual(len(result.attrs['data_info']['warnings']), 2)

    def test_request_shape_failure_and_cleanup(self):
        from ibapi.client import EClient
        original_wait = Event.wait
        for mode in ('success', 'error', 'timeout', 'empty'):
            disconnected = Event()
            requests = []

            def history(client, *args):
                requests.append(args)
                if mode == 'timeout':
                    return
                if mode == 'error':
                    client.error(1, 0, 162, 'Missing permissions')
                    return
                if mode == 'success':
                    client.historicalData(1, bar('2024-07-08T13:30:00Z'))
                    client.historicalData(1, bar('2024-07-08T13:31:00Z'))
                client.historicalDataEnd(1, '', '')

            def wait(event, timeout=None):
                return False if timeout == 45 and mode == 'timeout' else original_wait(event, timeout)

            with self.subTest(mode=mode), patch.object(EClient, 'connect', lambda client, *a, **kw: client.nextValidId(1)), patch.object(EClient, 'run', lambda client: disconnected.wait(5)), patch.object(EClient, 'disconnect', lambda client: disconnected.set()), patch.object(EClient, 'reqHistoricalData', history), patch.object(Event, 'wait', wait):
                if mode == 'success':
                    frame = download_minutes('AAPL', date(2024, 7, 8), 'NASDAQ')
                    self.assertEqual(len(frame), 2)
                    self.assertEqual(requests[0][2:9], ('20240709-00:00:00', '1 D', '1 min', 'TRADES', 1, 2, False))
                else:
                    with self.assertRaises(MarketDataUnavailableError):
                        download_minutes('AAPL', date(2024, 7, 8))
            self.assertTrue(disconnected.is_set())


if __name__ == '__main__':
    unittest.main()
