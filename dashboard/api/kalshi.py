"""Public Kalshi data and hypothetical binary-contract sizing. No order execution."""
from datetime import datetime, timezone
import json
from math import isfinite
from dashboard.kalshi.fairvalue import size_trade as calculate_trade
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict

router = APIRouter(prefix='/kalshi', tags=['Kalshi research'])
BASE_URL = 'https://external-dashboard.api.kalshi.com/trade-api/v2'


def fetch_public(params):
    try:
        with urlopen(BASE_URL + '/markets?' + urlencode(params), timeout=12) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get('markets'), list):
            raise ValueError('Invalid response')
        return data
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(502, 'Kalshi data is unavailable. Retry later; no substitute prices are used.') from exc


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


@router.get('/markets')
def markets(series: str = Query('', max_length=100, pattern=r'^[A-Za-z0-9-]*$'),
            cursor: str = Query('', max_length=2000)):
    params = {'status': 'open', 'limit': 100, 'mve_filter': 'exclude'}
    if series:
        params['series_ticker'] = series.upper()
    if cursor:
        params['cursor'] = cursor
    data = fetch_public(params)
    items = []
    for raw in data['markets']:
        if raw.get('market_type') != 'binary':
            continue
        item = {key: raw.get(key) for key in ('ticker', 'event_ticker', 'title', 'yes_sub_title',
                'status', 'close_time', 'rules_primary', 'rules_secondary')}
        for key in ('yes_bid', 'yes_ask', 'no_bid', 'no_ask'):
            value = number(raw.get(key + '_dollars'))
            item[key] = value if value is not None and 0 < value < 1 else None
        item['volume'] = number(raw.get('volume_fp'))
        items.append(item)
    return {'markets': items, 'cursor': data.get('cursor') or '',
            'fetched_at': datetime.now(timezone.utc).isoformat()}


class SizingRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    probability: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    price: float = Field(gt=0, lt=1)
    cost_allowance: float = Field(ge=0, lt=1)
    bankroll: float = Field(gt=0, le=1e9)
    available_cash: float = Field(ge=0, le=1e9)
    existing_event_risk: float = Field(ge=0, le=1e9)
    kelly_fraction: float = Field(gt=0, le=1)
    trade_cap: float = Field(gt=0, le=1)
    event_cap: float = Field(gt=0, le=1)


@router.post('/size')
def size_trade(r: SizingRequest):
    try:
        return calculate_trade(**r.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# Recorder endpoints are read-only with respect to the exchange.
class RecordingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    minutes: int = Field(default=30, ge=1, le=120)


@router.get('/btc-research')
def btc_research():
    from dashboard.kalshi.recorder import recorder
    return recorder.status()


@router.post('/btc-research/start')
def start_btc_research(request: RecordingRequest):
    from dashboard.kalshi.recorder import recorder
    try:
        return {'session_id': recorder.start(request.minutes)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/btc-research/stop')
def stop_btc_research():
    from dashboard.kalshi.recorder import recorder
    recorder.stop()
    return {'message': 'Stop requested. The current connection will close shortly.'}
