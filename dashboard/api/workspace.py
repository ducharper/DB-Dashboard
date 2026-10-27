"""Durable local strategy records, portfolio snapshots and position annotations."""
from contextlib import closing
from datetime import datetime, timezone
import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from dashboard.api.history import connect
from dashboard.backtester.errors import MarketDataUnavailableError

router = APIRouter()


def now():
    return datetime.now(timezone.utc).isoformat()


def database():
    db = connect()
    try:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS strategy_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (id TEXT PRIMARY KEY, captured_at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS position_notes (account TEXT NOT NULL, contract_id INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(account, contract_id));
        ''')
        return db
    except Exception:
        db.close()
        raise


class StrategyRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(default='1', min_length=1, max_length=40)
    status: Literal['research', 'paper', 'live', 'paused', 'archived'] = 'research'
    rules: str = Field(default='', max_length=20000)
    parameters: str = Field(default='', max_length=10000)
    risk_plan: str = Field(default='', max_length=10000)


class PositionNote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account: str = Field(min_length=1, max_length=100)
    contract_id: int = Field(gt=0)
    strategy_id: str | None = None
    thesis: str = Field(default='', max_length=10000)
    invalidation: str = Field(default='', max_length=10000)


@router.get('/strategies')
def strategies():
    with closing(database()) as db:
        return [json.loads(row['payload']) for row in db.execute('SELECT payload FROM strategy_records ORDER BY rowid DESC')]


def store_strategy(record, strategy_id, existing=False):
    payload = dict(record.model_dump(), id=strategy_id, updated_at=now())
    with closing(database()) as db, db:
        if existing and not db.execute('SELECT 1 FROM strategy_records WHERE id=?', (strategy_id,)).fetchone():
            raise HTTPException(404, 'Strategy not found.')
        db.execute('INSERT INTO strategy_records VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (strategy_id, json.dumps(payload)))
    return payload


@router.post('/strategies', status_code=201)
def create_strategy_record(record: StrategyRecord):
    return store_strategy(record, str(uuid4()))


@router.put('/strategies/{strategy_id}')
def edit_strategy_record(strategy_id: str, record: StrategyRecord):
    return store_strategy(record, strategy_id, True)


@router.get('/portfolio')
def portfolio():
    with closing(database()) as db:
        row = db.execute('SELECT payload FROM portfolio_snapshots ORDER BY captured_at DESC, rowid DESC LIMIT 1').fetchone()
        notes = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM position_notes')]
    return {'snapshot': json.loads(row['payload']) if row else None, 'notes': notes}


@router.post('/portfolio/refresh')
def refresh_portfolio():
    from dashboard.backtester.ibkr_portfolio import fetch_portfolio
    try:
        snapshot = fetch_portfolio()
    except MarketDataUnavailableError as exc:
        raise HTTPException(502, str(exc)) from exc
    snapshot.update(id=str(uuid4()), captured_at=now())
    with closing(database()) as db, db:
        db.execute('INSERT INTO portfolio_snapshots VALUES (?,?,?)', (snapshot['id'], snapshot['captured_at'], json.dumps(snapshot, allow_nan=False)))
    return portfolio()


@router.put('/portfolio/notes')
def save_position_note(note: PositionNote):
    with closing(database()) as db, db:
        if note.strategy_id and not db.execute('SELECT 1 FROM strategy_records WHERE id=?', (note.strategy_id,)).fetchone():
            raise HTTPException(422, 'Choose an existing strategy.')
        # Restrict annotations to a real contract/account observed in a saved snapshot.
        snapshots = db.execute('SELECT payload FROM portfolio_snapshots').fetchall()
        known = any(any(a['account'] == note.account and any(p['contract_id'] == note.contract_id for p in a['positions']) for a in json.loads(row['payload'])['accounts']) for row in snapshots)
        if not known:
            raise HTTPException(404, 'This position has not been observed in a portfolio snapshot.')
        payload = dict(note.model_dump(), updated_at=now())
        db.execute('INSERT INTO position_notes VALUES (?,?,?) ON CONFLICT(account,contract_id) DO UPDATE SET payload=excluded.payload', (note.account, note.contract_id, json.dumps(payload)))
    return payload

