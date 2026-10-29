# Bitcoin historical research

Run from the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m dashboard.kalshi.research.run --start 2026-10-26T14:00:00Z --end 2026-10-26T15:00:00Z
```

Times are UTC. The range selects contracts closing after start and at or before end.
The downloader includes earlier prices for estimating volatility. Existing Windows user
environment settings are read automatically. Private keys and signed headers are never cached.

The first run downloads BRTI and Kalshi contracts/quotes. Rerun with --offline to use
the saved dataset. Large historical ranges may require many paginated requests.
Requests are read-only. No orders are placed.

## Outputs

Outputs are under data/kalshi_research/<start_epoch>_<end_epoch>/:
- dataset.json: the source data used by the run.
- observations.csv: minute-boundary and final-minute predictions, including mean, sd, z and quote eligibility.
- validation.csv: the updated validator scorecard, grouped by seconds remaining.
- trades.csv: first qualifying trade per contract, assuming candle-close fills.
- stressed_trades.csv: separate replay with --slippage added to entry costs.
- skipped.csv: rejected observations and reasons.
- settlement_audit.csv: sampled opening/closing averages alongside published fields.
- report.json: configuration, P&L, drawdown, probability scores and limitations.

Each rerun replaces results for the same date range. Archive the folder before comparing
parameter experiments. Raw responses are cached separately with request URLs and download times.

## Assumptions

The current model assumes zero-drift Brownian dollar-price changes. Volatility uses fairvalue.ewma_sigma: five-second changes, ten-minute half-life,
and a two-hour contiguous warm-up (--lookback). Missing whole-second observations
reset the estimator and warm-up; they are never filled. At decision time t, the
latest admitted price is the exact whole-second print at t-1. Settlement uses
close-60 through close-1. Thus model tau=close-t counts remaining future prints.
Only greater/greater_or_equal settled binary contracts with a numeric floor_strike
are included. The published final strike is assumed known by the decision time.
This historical metadata assumption must be audited against contract rules.

Decisions occur after completed minute candles, from after the nominal opening until
60 seconds before close. Additional predictions at 30 and 10 seconds remaining support validation only.
They never use stale minute quotes to simulate purchases. Both quote availability
at the boundary and fills at the candle close are approximations: there is no historical
depth or latency model. Signal threshold defaults to 2 cents, with one contract per
entry and one entry per window, held to settlement. Fee coefficient defaults to 0.07
and rounds each order's fee up to a cent. Verify series/date-specific fees and use
--fee-rate to override. Slippage stress defaults to 1 cent per contract.

Settlement averages in the audit are diagnostics, not reconstructed official results.
BRTI sampling/rounding and the contract's exact comparison rules must be verified.
Actual Kalshi outcomes determine P&L. No inferred outcome replaces a missing outcome.

Brier score is average squared probability error (lower is better).
Calibration compares predicted probabilities with observed win frequencies.
The market midpoint is a descriptive comparator, not a fill price or guaranteed true probability.
Predictions within a contract are dependent; the report makes no significance claim.
Earlier/later chronological results are descriptive; the later set is a holdout only
if it was not used to choose parameters. One hour is a plumbing check, not validation.

## Files

history.py downloads; observations.py builds causal inputs; backtest.py applies the
entry rule; validate.py scores predictions; run.py connects these pieces.
The model remains in ../fairvalue.py and live recording remains in ../recorder.py.

Documentation:
- https://docs.kalshi.com/cfbenchmarks/rest-passthrough
- https://docs.kalshi.com/getting_started/historical_data
- https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks

Tests:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_kalshi_research.py -v
```

The validator consumes a DataFrame made from the same observation rows used by
the backtester. p_market is the matching bid/ask midpoint, not a last-trade fill.
PASS means the diagnostics did not flag a problem; it is not a profitability verdict.
Final-minute probabilities retain the model's continuous-price threshold approximation;
settlement rounding and strict/inclusive ties are not explicitly modelled.

Download pacing: uncached requests run sequentially, at least one second apart.
HTTP 429 slows subsequent requests and triggers up to seven retries, with increasing
waits and support for Retry-After (seconds or HTTP date). Cached successful responses
are reused immediately. Rerun the same command after an interrupted download; do not
use --offline until dataset.json has been saved successfully. Avoid simultaneous
research downloads or other heavy API consumers on the same account.
