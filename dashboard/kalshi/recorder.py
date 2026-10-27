"""Append-only research tape for KXBTC15M. No orders, positions or balances."""
import base64
from contextlib import closing
from datetime import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
import time
from uuid import uuid4

from dashboard.paths import PROJECT_ROOT as ROOT
WS_URL = 'wss://external-api-ws.kalshi.com/trade-api/ws/v2'


def database_path():
    return Path(os.environ.get('KALSHI_RESEARCH_DB_PATH', ROOT / 'data' / 'kalshi_research.sqlite3'))


def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, started_ms INTEGER, ended_ms INTEGER, state TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS frames (
          id INTEGER PRIMARY KEY, session_id TEXT, connection_id TEXT,
          received_ms INTEGER, monotonic_ns INTEGER, kind TEXT, source_ms INTEGER,
          value REAL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS frames_session ON frames(session_id, id);
        CREATE INDEX IF NOT EXISTS frames_kind ON frames(session_id, kind, source_ms);
    ''')
    return db


def append_frame(session, connection, frame, received_ms=None):
    received_ms = received_ms if received_ms is not None else int(time.time()*1000)
    kind = frame.get('type', 'unknown')
    source, value = None, None
    if kind == 'cfbenchmarks_value' and frame.get('msg', {}).get('index_id') == 'BRTI':
        try:
            data = frame['msg']['data']
            data = json.loads(data) if isinstance(data, str) else data
            source, value = int(data['time']), float(data['value'])
            if not math.isfinite(value) or value <= 0 or source <= 0:
                raise ValueError('Invalid observation')
        except (KeyError, ValueError, TypeError):
            source, value, kind = None, None, 'invalid_brti'
    with closing(connect()) as db, db:
        db.execute('INSERT INTO frames(session_id,connection_id,received_ms,monotonic_ns,kind,source_ms,value,payload) VALUES (?,?,?,?,?,?,?,?)',
                   (session, connection, received_ms, time.monotonic_ns(), kind, source, value,
                    json.dumps(frame, allow_nan=False)))


def window_coverage(rows, end_ms):
    """Research convention (end-60s, end], one source observation per second.

    Repeated source seconds do not increase coverage. Conflicting values are
    flagged rather than silently treated as a complete settlement average.
    """
    buckets = {}
    conflicts = 0
    for row in rows:
        ts, value = row['source_ms'], row['value']
        if ts is None or value is None or not end_ms-60000 < ts <= end_ms:
            continue
        second = math.ceil(ts / 1000)
        if second in buckets and buckets[second] != value:
            conflicts += 1
        else:
            buckets[second] = value
    expected = set(range(end_ms//1000-59, end_ms//1000+1))
    missing = sorted(expected - buckets.keys())
    return {'end_ms': end_ms, 'observed_seconds': len(buckets), 'missing_seconds': len(missing),
            'conflicts': conflicts, 'complete': not missing and not conflicts,
            'observed_average': sum(buckets.values())/len(buckets) if buckets else None}


def configuration():
    return {'credentials_configured': bool(os.environ.get('KALSHI_API_KEY_ID') and os.environ.get('KALSHI_PRIVATE_KEY_PATH')),
            'signing_available': importlib.util.find_spec('cryptography') is not None,
            'websocket_available': importlib.util.find_spec('websockets') is not None}


def load_signer():
    config = configuration()
    if not config['credentials_configured']:
        raise ValueError('Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH locally, then restart the launcher.')
    if not config['signing_available'] or not config['websocket_available']:
        raise ValueError('Install requirements-kalshi.txt in the project virtual environment, then restart.')
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
    try:
        key = serialization.load_pem_private_key(Path(os.environ['KALSHI_PRIVATE_KEY_PATH']).read_bytes(), password=None)
        if not isinstance(key, (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)):
            raise ValueError('Unsupported key type')
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError('Cannot load the configured RSA or Ed25519 PEM key. Check the local file.') from exc
    return key


def headers(key):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, ed25519
    stamp = str(int(time.time()*1000))
    message = (stamp + 'GET/trade-api/ws/v2').encode()
    signature = key.sign(message) if isinstance(key, ed25519.Ed25519PrivateKey) else key.sign(
        message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    return {'KALSHI-ACCESS-KEY': os.environ['KALSHI_API_KEY_ID'],
            'KALSHI-ACCESS-TIMESTAMP': stamp,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode()}


class Recorder:
    def __init__(self):
        self.lock = Lock()
        self.stop_event = Event()
        self.thread = None
        self.session = None

    def start(self, minutes=30):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('A recording is already running.')
            key = load_signer()
            session = str(uuid4())
            with closing(connect()) as db, db:
                db.execute('INSERT INTO sessions VALUES (?,?,NULL,?,NULL)', (session, int(time.time()*1000), 'starting'))
            self.session = session
            self.stop_event.clear()
            self.thread = Thread(target=self.run, args=(session, key, minutes), daemon=True)
            self.thread.start()
            return session

    def stop(self):
        self.stop_event.set()

    def set_state(self, session, state, error=None, finished=False):
        with closing(connect()) as db, db:
            db.execute('UPDATE sessions SET state=?,error=?,ended_ms=? WHERE id=?',
                       (state, error, int(time.time()*1000) if finished else None, session))

    def run(self, session, key, minutes):
        from websockets.sync.client import connect as ws_connect
        from dashboard.api.kalshi import fetch_public
        deadline = time.monotonic() + minutes*60
        retries = 0
        try:
            while not self.stop_event.is_set() and time.monotonic() < deadline:
                connection = str(uuid4())
                try:
                    # Metadata is preserved each connection, including rules and strike fields.
                    metadata = fetch_public({'series_ticker': 'KXBTC15M', 'status': 'open', 'limit': 100})
                    markets = metadata['markets']
                    append_frame(session, connection, {'type': 'market_metadata', 'markets': markets})
                    tickers = [m['ticker'] for m in markets if m.get('market_type') == 'binary']
                    if not tickers:
                        self.set_state(session, 'waiting', 'No open KXBTC15M markets. Retrying.')
                        self.stop_event.wait(10)
                        continue
                    with ws_connect(WS_URL, additional_headers=headers(key), open_timeout=10,
                                    close_timeout=2, ping_interval=20, ping_timeout=20, max_queue=1024) as ws:
                        for command_id, params in enumerate([
                            {'channels': ['cfbenchmarks_value'], 'index_ids': ['BRTI']},
                            {'channels': ['orderbook_delta'], 'market_tickers': tickers},
                            {'channels': ['ticker'], 'market_tickers': tickers},
                        ], 1):
                            ws.send(json.dumps({'id': command_id, 'cmd': 'subscribe', 'params': params}))
                        self.set_state(session, 'recording')
                        sequences = {}
                        connected_at = time.monotonic()
                        # Refresh discovery by reconnecting every 5 minutes. Every reconnect
                        # is explicit on tape and starts with new order-book snapshots.
                        refresh_at = min(time.monotonic()+300, deadline)
                        # Reconnect just after the earliest market close for rollover.
                        closes = []
                        for m in markets:
                            try:
                                closes.append(datetime.fromisoformat(m['close_time'].replace('Z', '+00:00')).timestamp())
                            except (KeyError, ValueError, TypeError):
                                pass
                        future = [t for t in closes if t > time.time()]
                        if future:
                            refresh_at = min(refresh_at, time.monotonic()+min(future)-time.time()+2)
                        while not self.stop_event.is_set() and time.monotonic() < refresh_at:
                            try:
                                raw = ws.recv(timeout=1)
                            except TimeoutError:
                                continue
                            received = int(time.time()*1000)
                            frame = json.loads(raw)
                            append_frame(session, connection, frame, received)
                            if frame.get('type') == 'error':
                                raise RuntimeError('Subscription rejected; inspect recorded error frame.')
                            sid, seq = frame.get('sid'), frame.get('seq')
                            if sid is not None and isinstance(seq, int):
                                if sid in sequences and seq != sequences[sid]+1:
                                    append_frame(session, connection, {'type': 'sequence_gap', 'sid': sid,
                                                 'previous': sequences[sid], 'actual': seq})
                                    raise RuntimeError('Sequence gap; reconnecting for fresh snapshots.')
                                sequences[sid] = seq
                            if time.monotonic() - connected_at >= 30:
                                retries = 0
                    append_frame(session, connection, {'type': 'connection_end'})
                except Exception as exc:
                    # Never serialize exception text that could contain auth headers.
                    retries += 1
                    reason = f'Connection interrupted ({type(exc).__name__}); retry {retries}.'
                    append_frame(session, connection, {'type': 'connection_error', 'reason': reason})
                    self.set_state(session, 'reconnecting', reason)
                    if retries >= 5:
                        self.set_state(session, 'failed', reason, finished=True)
                        return
                    self.stop_event.wait(min(2**retries, 30, max(0, deadline-time.monotonic())))
            self.set_state(session, 'stopped' if self.stop_event.is_set() else 'completed', finished=True)
        except Exception:
            # Storage failures must stop collection rather than silently discard data.
            try:
                self.set_state(session, 'failed', 'Recorder stopped because data could not be saved.', finished=True)
            except sqlite3.Error:
                pass

    def status(self):
        with self.lock:
            running = bool(self.thread and self.thread.is_alive())
        with closing(connect()) as db:
            latest = db.execute('SELECT * FROM sessions ORDER BY started_ms DESC LIMIT 1').fetchone()
            if not latest:
                return {'running': running, 'configuration': configuration(), 'session': None,
                        'counts': {}, 'windows': [], 'latest_brti': None, 'metadata': []}
            session = dict(latest)
            if not running and session['ended_ms'] is None:
                session['state'] = 'interrupted'
            counts = dict(db.execute('SELECT kind,COUNT(*) FROM frames WHERE session_id=? GROUP BY kind', (session['id'],)).fetchall())
            latest_brti = db.execute('SELECT source_ms,received_ms,value FROM frames WHERE session_id=? AND source_ms IS NOT NULL ORDER BY source_ms DESC LIMIT 1', (session['id'],)).fetchone()
            rows = db.execute('SELECT source_ms,value FROM frames WHERE session_id=? AND source_ms IS NOT NULL ORDER BY id DESC LIMIT 7200', (session['id'],)).fetchall()
            metadata = db.execute("SELECT payload FROM frames WHERE session_id=? AND kind='market_metadata' ORDER BY id DESC LIMIT 1", (session['id'],)).fetchone()
        end = math.ceil((latest_brti['source_ms'] if latest_brti else int(time.time()*1000))/900000)*900000
        windows = [window_coverage(rows, end-i*900000) for i in range(4)]
        return {'running': running, 'configuration': configuration(), 'session': session, 'counts': counts,
                'latest_brti': dict(latest_brti) if latest_brti else None, 'windows': windows,
                'metadata': json.loads(metadata['payload'])['markets'] if metadata else []}


recorder = Recorder()
