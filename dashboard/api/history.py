"""Local run storage. No market data is downloaded when reopening a run."""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from dashboard.paths import DATA_ROOT
from uuid import uuid4


def database_path() -> Path:
    return Path(os.environ.get('BACKTEST_DB_PATH', DATA_ROOT / 'backtests.sqlite3'))


def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, completed_at TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        )''')
        connection.commit()
    except Exception:
        connection.close()
        raise
    return connection


def save_run(request: dict, result: dict) -> tuple[str, str]:
    run_id, completed_at = str(uuid4()), datetime.now(timezone.utc).isoformat()
    with closing(connect()) as db, db:
        db.execute('INSERT INTO runs (id, completed_at, request, result) VALUES (?, ?, ?, ?)',
                   (run_id, completed_at, json.dumps(request, allow_nan=False), json.dumps(result, allow_nan=False)))
    return run_id, completed_at


def list_runs(limit: int, offset: int) -> list[dict]:
    with closing(connect()) as db:
        rows = db.execute('SELECT id, completed_at, request FROM runs WHERE deleted = 0 ORDER BY completed_at DESC, id DESC LIMIT ? OFFSET ?', (limit, offset)).fetchall()
    return [dict(id=row['id'], completedAt=row['completed_at'], request=json.loads(row['request'])) for row in rows]


def get_run(run_id: str) -> dict | None:
    with closing(connect()) as db:
        row = db.execute('SELECT * FROM runs WHERE id = ? AND deleted = 0', (run_id,)).fetchone()
    if row is None:
        return None
    return dict(id=row['id'], completedAt=row['completed_at'], request=json.loads(row['request']), result=json.loads(row['result']))


def delete_run(run_id: str) -> bool:
    # Soft deletion keeps accidental removals recoverable in the database.
    with closing(connect()) as db, db:
        return db.execute('UPDATE runs SET deleted = 1 WHERE id = ? AND deleted = 0', (run_id,)).rowcount == 1
