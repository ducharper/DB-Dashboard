# One-click startup

Double-click **Start Backtester.vbs** in this folder. A small launcher window starts the app and opens your browser. Keep the launcher open; use **Stop & close** when finished. You can create a Windows shortcut to that file on your desktop.

The app runs only on this computer at http://127.0.0.1:8765. No hosting account or separate terminals are needed. First startup (and startup after frontend changes) builds the website; subsequent launches reuse the build. Starting a second launcher opens the existing app instead of starting another server. Closing an extra launcher does not stop the original one.

Prerequisites: the project's `.venv` with its existing Python dependencies, Node.js, and installed frontend dependencies. If dependencies are missing, run `npm install` inside `frontend` once. The launcher never installs software automatically. Startup failures are reported in its window; details are in `data/launcher.log`.

## Trading workspace: first milestone

The app now opens on **Portfolio**. Open paper TWS on port **7497**, keep **Read-Only API** enabled, then click **Refresh from TWS**. The portfolio reader uses client ID **51**, independently of historical-price downloads. It reads accessible accounts (up to 10), account values and positions, waits for completed downloads, saves a snapshot, and disconnects. No orders are submitted or changed.

This is manual snapshot refresh, not a live stream. A saved snapshot is always labeled with its capture time; failed refreshes leave it unchanged. Prices may be delayed. Paper identification uses the IBKR DU account prefix; other accounts are labeled live/unverified rather than assumed paper. Currency values are kept separate. P&L is TWS-reported, not a cash-flow-adjusted return or a strategy-attribution calculation.

Use **Strategies** to create/edit named strategy records, version labels, status, rules, parameters and risk plans. These are research records, not executable strategies; a “live” status does not activate trading. Version labels are manual, and editing updates the record rather than creating immutable version history. Use a position's **Add note / Edit note** button to attach a strategy, thesis and invalidation/review plan. Notes are keyed by account plus contract ID, and persist across refreshes, restarts, and closing/reopening the same instrument. A position can have one manual strategy label; multi-strategy allocation is not implemented.

Account snapshots, strategy records and position notes are stored in the existing local SQLite database. It now contains sensitive account data: keep backups private, do not commit it, and do not expose this unauthenticated app beyond localhost. No account data is uploaded. Strategy/position editors require explicit Save; switching workspace tabs retains unsaved edits, but reloading the browser discards them. The older **Journal** remains browser-local and is not migrated or included in the SQLite backup.

**Research**, **Saved experiments**, and **Journal** preserve the previous tools. New Python backtests record their engine. Existing NinjaTrader research source is unchanged; NinjaTrader results importing, risk alerts, strategy attribution, historical return analytics, and order execution are not part of this milestone. A real NinjaTrader trade export is needed before building its importer.

Verification: backend tests use temporary databases and simulated account callbacks. Run `python -m unittest discover -s tests` in the project environment. Browser checks used an isolated demonstration database. The first live portfolio verification could not connect to TWS (502), so refresh against your logged-in paper session to verify actual account values.

## Backtest results

Every successful API backtest automatically saves its request settings, summary, equity observations and completed trades in **data/backtests.sqlite3**. Use **Saved runs** to reopen one after restarting or refreshing. Opening a run restores the form settings too. Reopening does not contact the market-data provider.

Runs created before this feature cannot be recovered from past browser sessions. If you stop waiting for a request, the server may still complete and save it; use **Refresh** in history to check.

Delete removes a run from the visible history after confirmation. Records are soft-deleted in SQLite, not physically erased. There is currently no restore button.

The `data` folder is ignored by Git. To back up saved runs, stop the launcher and copy `data/backtests.sqlite3` somewhere safe. GitHub backups of code do **not** include these results. Do not put the local app directly on the public internet: authentication is not implemented.

## IBKR historical prices

In **Edit parameters**, select **Interactive Brokers · TWS** (default for new forms). Keep paper TWS logged in with socket clients enabled on **7497** and **Read-Only API** checked. The app uses localhost and client ID **49**; it never submits orders. Yahoo remains an explicit alternative. Failed IBKR requests never fall back silently.

Initially supported: daily regular-session prices for USD stocks and ETFs via SMART. For ambiguous symbols, specify the primary exchange (NASDAQ, NYSE, etc.). Other currencies, futures, options and intraday bars are not supported. Historical availability depends on permissions, subscriptions and instrument history; it is not guaranteed.

IBKR TRADES prices adjust for splits but **exclude dividends**; Yahoo adjusts for both. Compare results using the same provider. Actual coverage, bar count, retrieval time, price basis and warnings are saved with each run. Today's unfinished session is excluded. Ranges download in overlapping yearly segments (maximum 20 years). Errors or empty segments prevent partial backtests. Only one IBKR download runs at a time. No credentials are stored.

Restart the launcher after updating. Old saved runs remain readable and default to Yahoo when reopened. Saved results work without TWS; new calculations do not use cached prices.

## Development

### One-minute research data

`download_intraday.py` retrieves one completed US stock/ETF session from paper TWS as one-minute OHLCV bars. Keep TWS logged in on port 7497 with Read-Only API enabled. It uses client ID 50 and sends no orders.

```powershell
.\.venv\Scripts\python.exe download_intraday.py --symbol AAPL --date 2026-10-05 --exchange NASDAQ
```

Choose a completed trading date before today. Each successful download creates a new folder under `data/intraday/` with `bars.csv` and `metadata.json`. CSV timestamps mark the **start** of the minute and include UTC and America/New_York offsets. Metadata records the request, source, coverage and warnings. Prices are split-adjusted TRADES and exclude dividends. Availability depends on IBKR permissions and history.

Missing minutes are never filled. Coverage other than the normal 390 regular-session minutes produces a warning; early closes, halts and missing data require review. Errors and timeouts do not export partial downloads. This downloader has no automatic retries or bulk scheduling.

The dashboard now supports **Bar size → 1 minute** with IBKR. Choose completed sessions, with an exclusive end date and at most 31 calendar days. It downloads each weekday in sequence; holidays, early closes and incomplete sessions stop the run rather than silently skipping data. Old saved runs remain daily. Restart the launcher after updating.

Intraday signals restart each session and windows count bars (minutes). Signals calculated from a completed bar fill at the next bar's open. Positions liquidate at 15:59 open, so no overnight exposure is carried. Costs apply to each buy and sell; the model uses fractional shares with no leverage. These are estimated fills without observed spreads or liquidity constraints. Charts mark bars by their start time while valuing the portfolio at the bar close; trade timestamps are actual simulated fill times. All dashboard intraday times use New York time.

Annualized return, volatility, Sharpe and Sortino use compounded daily returns and 252 sessions/year; they are withheld for fewer than 20 sessions. Twenty sessions is only a display minimum, not evidence of a reliable strategy. Buy-and-hold starts at the first session open and includes overnight returns. Saved runs retain minute timestamps and interval settings.

Minute OHLCV does not contain bid/ask spreads, auction imbalances, or within-minute volume timing. Testing the first-second volume claim requires finer data.

### Optional IBKR connection check

The standalone TWS connectivity check is `check_ibkr.py`. It connects only to local port 7497 with client ID 47, requests server time, then disconnects. Keep **Read-Only API** checked. This check does not verify historical-data permissions; choose IBKR in the app to run a historical-data backtest.

Install the Python library from the official IBKR API installer, not the unrelated PyPI download. For the locally installed version:

```powershell
.\.venv\Scripts\python.exe -m pip install "C:/TWS API 1051.01/source/pythonclient"
.\.venv\Scripts\python.exe check_ibkr.py
```

This SDK installs `ibapi==1051.1` and requires `protobuf==5.29.5`. The latter replaces the previously installed protobuf version in this project's environment. Adjust the source path if you install another SDK version. No account credentials are stored by the check.

### Frontend and backend

The previous two-terminal Vite/API workflow still works on ports 5173/8000. The launcher instead serves the built frontend and API together on port 8765. Stop and restart the launcher after changing Python code; frontend changes are rebuilt on the next launch.

Storage tests: `.venv\Scripts\python.exe -m unittest discover -s tests -p test_saved_runs.py` (uses temporary databases and synthetic prices, not your saved runs).
