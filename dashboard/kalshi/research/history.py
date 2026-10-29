"""Read-only Kalshi downloader. Raw responses are cached without credentials."""
import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import HTTPError

BASE = "https://external-api.kalshi.com/trade-api/v2"

def epoch(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Dates must include a timezone, e.g. 2026-10-26T14:00:00Z")
    return int(dt.timestamp())

class Client:
    def __init__(self, cache, offline=False):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.key = None
        self.next_request = 0.0
        self.request_interval = 1.0

    def headers(self, path):
        if self.key is None:
            for name in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH"):
                if not os.environ.get(name) and os.name == "nt":
                    import winreg
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                            os.environ[name] = winreg.QueryValueEx(reg, name)[0]
                    except OSError:
                        pass
            if not all(os.environ.get(n) for n in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH")):
                raise ValueError("Configure KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH.")
            from cryptography.hazmat.primitives import serialization
            self.key = serialization.load_pem_private_key(
                Path(os.environ["KALSHI_PRIVATE_KEY_PATH"]).read_bytes(), password=None)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, ed25519
        stamp = str(int(time.time()*1000))
        message = (stamp + "GET/trade-api/v2" + path).encode()
        signature = self.key.sign(message) if isinstance(self.key, ed25519.Ed25519PrivateKey) else self.key.sign(
            message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
        return {"KALSHI-ACCESS-KEY": os.environ["KALSHI_API_KEY_ID"],
                "KALSHI-ACCESS-TIMESTAMP": stamp,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode()}

    @staticmethod
    def pause(seconds):
        # Long server-directed waits are broken into short sleeps.
        while seconds > 0:
            part = min(seconds, 30.0)
            time.sleep(part)
            seconds -= part

    @staticmethod
    def retry_delay(error, attempt):
        backoff = min(60.0, 5.0 * 2 ** attempt)
        hint = error.headers.get("Retry-After") if error.headers else None
        if hint:
            try:
                delay = float(hint)
            except (TypeError, ValueError):
                try:
                    delay = parsedate_to_datetime(hint).timestamp() - time.time()
                except (ValueError, TypeError, OverflowError):
                    delay = 0
            if delay > backoff:
                return delay
        return backoff

    def get(self, path, params=None, authenticated=False, fresh=False):
        url = BASE + path + ("?" + urlencode(sorted((params or {}).items())) if params else "")
        target = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if target.exists() and (not fresh or self.offline):
            return json.loads(target.read_text())["response"]
        if self.offline:
            raise ValueError("Missing cached response for " + path)
        for attempt in range(8):
            self.pause(max(0.0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + self.request_interval
            try:
                headers = self.headers(path) if authenticated else {}
                with urlopen(Request(url, headers=headers), timeout=30) as response:
                    data = json.load(response)
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps({"url": url, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                                                  "response": data}), encoding="utf-8")
                temporary.replace(target)
                return data
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 7:
                    delay = self.retry_delay(exc, attempt)
                    if exc.code == 429:
                        self.request_interval = min(10.0, self.request_interval * 2)
                    self.next_request = max(self.next_request, time.monotonic() + delay)
                    print(f"Kalshi HTTP {exc.code}: waiting {delay:.0f}s before retry "
                          f"{attempt+1}/7 (requests spaced {self.request_interval:.0f}s apart).", flush=True)
                    continue
                raise ValueError(f"Kalshi HTTP {exc.code} at {path}; check access/service status.") from None

    def pages(self, path, params):
        cursor, seen = "", set()
        while True:
            data = self.get(path, {**params, **({"cursor": cursor} if cursor else {})}, fresh=True)
            yield from data["markets"]
            cursor = data.get("cursor")
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("Repeated pagination cursor")
            seen.add(cursor)

def download(client, start, end, lookback=300):
    markets = {}
    cutoff_data = client.get("/historical/cutoff", fresh=True)
    cutoff = epoch(cutoff_data["market_settled_ts"])
    # Query both tiers: archived markets do not support close-time filters.
    for tier in ("live", "historical"):
        if tier == "historical" and start >= cutoff:
            continue
        print("Fetching", tier, "market records...", flush=True)
        path = "/markets" if tier == "live" else "/historical/markets"
        params = {"series_ticker": "KXBTC15M", "limit": 1000}
        if tier == "live":
            params.update(min_close_ts=start, max_close_ts=end, status="settled")
        for market in client.pages(path, params):
            closing = epoch(market["close_time"])
            if start < closing <= end and market.get("result") in ("yes", "no"):
                markets[market["ticker"]] = {**market, "_tier": tier}
    if not markets:
        raise ValueError("No settled KXBTC15M contracts found in requested range.")
    def fetch_candles(pair):
        ticker, market = pair
        encoded = quote(ticker, safe="")
        path = (f"/historical/markets/{encoded}/candlesticks" if market["_tier"] == "historical"
                else f"/series/KXBTC15M/markets/{encoded}/candlesticks")
        closing = epoch(market["close_time"])
        result = client.get(path, {"start_ts": closing-900, "end_ts": closing,
                                  "period_interval": 1})["candlesticks"]
        return ticker, result
    candles = {}
    # Sequential requests share one pacing clock. Cached responses need no wait.
    for i, pair in enumerate(sorted(markets.items()), 1):
        ticker, values = fetch_candles(pair)
        candles[ticker] = values
        if i % 25 == 0 or i == len(markets):
            print(f"Quotes: {i}/{len(markets)} (including cached responses)", flush=True)
    ticks = []
    first = (min(epoch(m["close_time"])-900 for m in markets.values())-lookback-60)//3600*3600
    for hour in range(first, (end//3600+1)*3600, 3600):
        stamp = datetime.fromtimestamp(hour, timezone.utc).strftime("%Y-%m-%dT%H:00:00.000Z")
        print("BRTI:", stamp, flush=True)
        data = client.get("/cfbenchmarks/history/values",
                          {"id": "BRTI", "timespan": "HOUR", "timestamp": stamp}, authenticated=True)
        payload = data["data"]["payload"]
        if not isinstance(payload, list) or not payload:
            raise ValueError("BRTI history returned no observations")
        ticks.extend(payload)
    return {"markets": list(markets.values()), "candles": candles, "ticks": ticks}
