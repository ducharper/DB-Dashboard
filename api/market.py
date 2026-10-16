"""Small, cached public-market snapshot for the workspace landing page."""
from datetime import datetime, timezone
from math import isfinite
from threading import Lock
from time import monotonic

import yfinance as yf

_lock = Lock()
_cached = None
_expires = 0.0
INSTRUMENTS = [('SPY', 'S&P 500 ETF'), ('QQQ', 'Nasdaq-100 ETF'), ('IWM', 'Russell 2000 ETF')]


def market_snapshot():
    global _cached, _expires
    with _lock:
        if _cached is not None and monotonic() < _expires:
            return _cached
        items = []
        for symbol, name in INSTRUMENTS:
            try:
                frame = yf.download(symbol, period='1mo', interval='1d', auto_adjust=False,
                                    multi_level_index=False, progress=False, threads=False, timeout=8)
                points = [{'date': date.date().isoformat(), 'close': float(value)}
                          for date, value in frame['Close'].items() if isfinite(float(value)) and float(value) > 0]
                if len(points) < 2:
                    raise ValueError('Insufficient observations')
                last, previous = points[-1], points[-2]
                items.append({'symbol': symbol, 'name': name, 'points': points,
                              'price': last['close'], 'date': last['date'],
                              'change': last['close'] / previous['close'] - 1})
            except Exception:
                items.append({'symbol': symbol, 'name': name, 'points': [],
                              'price': None, 'date': None, 'change': None})
        _cached = {'items': items, 'fetched_at': datetime.now(timezone.utc).isoformat()}
        _expires = monotonic() + (300 if all(item['price'] is not None for item in items) else 60)
        return _cached
