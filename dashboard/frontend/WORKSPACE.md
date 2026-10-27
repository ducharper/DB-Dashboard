# Backtester workspace

The landing area is now a read-only Portfolio dashboard. Navigation includes Portfolio, Strategies, Research, Saved experiments and Journal. Portfolio/strategy APIs are in `dashboard/api/workspace.py`; IBKR snapshot callbacks are in `dashboard/backtester/ibkr_portfolio.py`. Refreshes are manual, complete snapshots are persisted to SQLite, and stale/offline viewing never implies an active connection. Position notes link account+contract IDs to manual strategy records. The existing Journal remains browser-local. See `START_HERE.md` for scope and privacy limitations.

For everyday use, double-click **Start Backtester.vbs** in the repository root. It builds the frontend when needed, starts the local app, and opens the browser. Use its launcher window to stop the app. See `../../START_HERE.md` for saved-run storage and backups.

The commands below remain available for development:

Start the API from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn dashboard.api.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd dashboard/frontend
npm run dev
```

Open the address printed by Vite. The development proxy forwards `/api/backtests` to Python on port 8000. Production hosting needs equivalent routing; the development proxy is not part of the build.

The dashboard supports all three strategies, summary metrics, value/return/drawdown charts, date filtering, and sortable/filterable completed trades with CSV export. Calculations still run in Python. Results retain the exact submitted settings, so editing the form does not silently change the displayed run.

Successful runs are saved in the local SQLite database and can be reopened from Saved runs after a refresh or restart. Open trades are excluded from the closed-trade ledger. Benchmark returns are before costs. Stopping a request stops waiting in the browser, not necessarily the Python calculation or automatic save.

## Verification

Read [DESIGN_GUIDELINES.md](DESIGN_GUIDELINES.md) before frontend design changes; it records the user's chosen design reference and its application to this workspace.

The default page requests `/api/market-snapshot` for SPY, QQQ, and IWM. The server caches Yahoo Finance daily bars for five minutes (one minute after a partial failure); the browser refreshes every five minutes while visible. These are dated daily snapshots, not a real-time quote feed. No API key is required. Provider failures display an unavailable state, and failed browser refreshes retain the previous chart with a stale-data notice.

Use `npm run build` and `npm run lint` for static checks.

`scripts/smoke.cjs` checks browser interactions with intercepted test responses, not live market data. It requires Playwright resolvable by Node and installed Microsoft Edge. Start Vite on port 5175 and run `node scripts/smoke.cjs`. Set `BACKTEST_URL` for another address, `BACKTEST_BROWSER` for another installed browser channel, or `BACKTEST_SCREENSHOT` to an absolute PNG output path. Playwright is not a production dependency.
