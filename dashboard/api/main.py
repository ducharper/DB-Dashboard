from math import isfinite
from dashboard.paths import PROJECT_ROOT, FRONTEND_ROOT
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from dashboard.api import history
from dashboard.api.workspace import router as workspace_router
from dashboard.api.kalshi import router as kalshi_router

from dashboard.api.schemas import BacktestRequest, BacktestResponse
from dashboard.api.strategy_factory import create_strategy
from dashboard.backtester.runner import run_backtest
from dashboard.backtester.errors import MarketDataUnavailableError

app = FastAPI(title="Trading Dashboard")

app.include_router(workspace_router)
app.include_router(workspace_router, prefix='/api')
app.include_router(kalshi_router)
app.include_router(kalshi_router, prefix='/api')

@app.exception_handler(sqlite3.Error)
@app.exception_handler(OSError)
async def workspace_storage_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Local storage or connection is unavailable. Changes may not have been saved; refresh to verify.'})

@app.get('/market-snapshot')
@app.get('/api/market-snapshot')
def read_market_snapshot():
    from dashboard.api.market import market_snapshot
    return market_snapshot()

@app.post("/backtests", response_model=BacktestResponse)
@app.post("/api/backtests", response_model=BacktestResponse)
def create_backtest(request: BacktestRequest) -> dict:
    strategy = create_strategy(request.strategy)

    try:
        result, summary, ledger = run_backtest(
            symbol=request.symbol,
            start=request.start.isoformat(),
            end=request.end.isoformat(),
            strategy=strategy,
            initial_cash=request.initial_cash,
            cost_bps=request.cost_bps,
            periods_per_year=request.periods_per_year,
            risk_free_rate=request.risk_free_rate,
            data_source=request.data_source,
            ibkr_primary_exchange=request.ibkr_primary_exchange,
            bar_size=request.bar_size,
        )
    except MarketDataUnavailableError as exception:
        raise HTTPException(
            status_code=502,
            detail=str(exception),
        ) from exception

    clean_summary = {}
    benchmark_equity = (
        request.initial_cash * (1 + result["Asset Returns"]).cumprod()
    )

    equity = []
    for row_number, (timestamp, row) in enumerate(result.iterrows()):
        equity.append({
            "date": timestamp.tz_convert('America/New_York').isoformat() if request.bar_size == '1 min' else timestamp.date().isoformat(),
            "strategy": float(row["Equity Curve"]),
            "benchmark": float(benchmark_equity.iloc[row_number]),
        })

    trades = []
    for _, row in ledger.iterrows():
        trades.append({
            "entry_date": row['Entry Date'].tz_convert('America/New_York').isoformat() if request.bar_size == '1 min' else row['Entry Date'].date().isoformat(),
            "exit_date": row['Exit Date'].tz_convert('America/New_York').isoformat() if request.bar_size == '1 min' else row['Exit Date'].date().isoformat(),
            "entry_price": float(row["Entry Price"]),
            "exit_price": float(row["Exit Price"]),
            "holding_period": int(row["Holding Period"]),
            "net_return": float(row["Net Return"]),
        })

    for name, value in summary.items():
        numeric_value = float(value)
        clean_summary[name] = (numeric_value if isfinite(numeric_value) else None)

    result = BacktestResponse.model_validate({
        "data_info": result.attrs.get('data_info'),
        "summary": clean_summary,
        "equity": equity,
        "trades": trades,
    }).model_dump(mode='json', exclude={'run_id', 'completed_at'})
    try:
        run_id, completed_at = history.save_run(request.model_dump(mode='json'), result)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, 'The calculation completed, but could not be saved. Check available disk space and data folder permissions.') from exc
    return {**result, 'run_id': run_id, 'completed_at': completed_at}


@app.get('/health')
def health():
    return {'app': 'practice-backtester', 'workspace': str(PROJECT_ROOT)}


@app.get('/runs')
@app.get('/api/runs')
def runs(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    try:
        return history.list_runs(limit, offset)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, 'Saved runs are unavailable. Check the local database.') from exc


@app.get('/runs/{run_id}')
@app.get('/api/runs/{run_id}')
def read_run(run_id: str):
    try:
        run = history.get_run(run_id)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, 'Saved runs are unavailable. Check the local database.') from exc
    if run is None:
        raise HTTPException(404, 'Saved run not found.')
    return run


@app.delete('/runs/{run_id}', status_code=204)
@app.delete('/api/runs/{run_id}', status_code=204)
def remove_run(run_id: str):
    try:
        deleted = history.delete_run(run_id)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, 'Could not remove the saved run.') from exc
    if not deleted:
        raise HTTPException(404, 'Saved run not found.')


# The launcher builds the frontend first, then serves everything on one local port.
frontend = FRONTEND_ROOT / 'dist'
if frontend.is_dir():
    app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
