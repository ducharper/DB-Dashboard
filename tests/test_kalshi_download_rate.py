"""Network-free checks for download pacing, retries, and cache reuse."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from dashboard.kalshi.research.history import Client

class DownloadRateTests(unittest.TestCase):
    def client(self, directory):
        client = Client(directory)
        client.pause = Mock()
        return client

    def response(self):
        return io.BytesIO(json.dumps({"ok": True}).encode())

    def test_429_honors_retry_after_and_reuses_successful_cache(self):
        with tempfile.TemporaryDirectory(dir="data/kalshi_research") as directory:
            client = self.client(directory)
            error = HTTPError("https://example.invalid", 429, "limited",
                              {"Retry-After": "17"}, None)
            with patch("dashboard.kalshi.research.history.time.monotonic", return_value=100), \
                 patch("dashboard.kalshi.research.history.urlopen",
                       side_effect=[error, self.response()]) as fetch:
                self.assertEqual(client.get("/test"), {"ok": True})
                self.assertEqual(client.pause.call_args_list[-1].args, (17.0,))
                self.assertEqual(client.request_interval, 2)
                self.assertEqual(client.get("/test"), {"ok": True})
                self.assertEqual(fetch.call_count, 2)

    def test_distinct_requests_are_paced(self):
        with tempfile.TemporaryDirectory(dir="data/kalshi_research") as directory:
            client = self.client(directory)
            with patch("dashboard.kalshi.research.history.time.monotonic", return_value=100), \
                 patch("dashboard.kalshi.research.history.urlopen",
                       side_effect=[self.response(), self.response()]):
                client.get("/first")
                client.get("/second")
            self.assertEqual(client.pause.call_args_list[-1].args, (1.0,))

    def test_retry_after_date(self):
        error = HTTPError("https://example.invalid",429,"limited",
                          {"Retry-After": "Thu, 01 Jan 1970 00:01:40 GMT"},None)
        with patch("dashboard.kalshi.research.history.time.time",return_value=70):
            self.assertEqual(Client.retry_delay(error,0),30)

    def test_failed_request_is_not_cached_and_retries_are_bounded(self):
        with tempfile.TemporaryDirectory(dir="data/kalshi_research") as directory:
            client = self.client(directory)
            error = HTTPError("https://example.invalid",429,"limited",{},None)
            with patch("dashboard.kalshi.research.history.urlopen",side_effect=error) as fetch:
                with self.assertRaisesRegex(ValueError,"429"):
                    client.get("/test")
                self.assertEqual(fetch.call_count,8)
            self.assertEqual(list(Path(directory).glob("*.json")),[])

    def test_authentication_is_recreated_for_each_attempt(self):
        with tempfile.TemporaryDirectory(dir="data/kalshi_research") as directory:
            client = self.client(directory)
            client.headers = Mock(return_value={})
            error = HTTPError("https://example.invalid",503,"unavailable",{},None)
            with patch("dashboard.kalshi.research.history.urlopen",
                       side_effect=[error,self.response()]):
                client.get("/test",authenticated=True)
            self.assertEqual(client.headers.call_count,2)
