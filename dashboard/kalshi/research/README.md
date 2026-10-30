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

Trade exports: trades.csv and stressed_trades.csv now use a compact reader-facing schema.
Detailed rows are retained in trades_detailed.csv and stressed_trades_detailed.csv.
Predicted win probability refers to the PURCHASED side (NO uses 1-p).
Money fields are USD; probabilities are fractions (0.70 means 70 percent).
Expected profit is after modelled entry costs. Result means the purchased side won.
Cumulative profit is ordered by settlement time. UTC entry times include the timezone.
Observation and validation files retain their diagnostic schemas.

## Probability calibration

Fit using an existing observations.csv and its adjacent report.json:

    .\.venv\Scripts\python.exe -m dashboard.kalshi.research.calibration --observations data/kalshi_research/1792382400_1792987200/observations.csv --output data/kalshi_research/calibration_oct19_25.json

This fits sigmoid(a + b * logit(p)). a adjusts YES bias; b adjusts confidence.
The objective is weighted log loss with a small fixed ridge penalty toward (0,1).
Every contract receives equal total weight; only predictions with tau >= 60 are fitted.
The 30-window minimum is an input guard, not evidence of reliability. Training scores
are in-sample. Endpoints are clipped to [0.0001,0.9999]. Coefficients are bounded
and the artifact records whether a bound was hit. No trading profit is optimized.

Test on later dates with --calibration data/kalshi_research/calibration_oct19_25.json.
The pipeline rejects overlapping training predictions and mismatched EWMA settings
or a changed fairvalue.py. It allows 60 seconds after the last training close for
outcome availability (a conservative research assumption, not guaranteed live availability).
The test dataset stays in the normal date folder. Calibrated results go in a separate
calibrated_<file-hash> subfolder with original_trades.csv and a comparison in report.json.
Both strategies see identical observations and retain identical trading settings.
The active probability is calibrated; p_raw retains the original. mean, sd and z
still describe the raw model distribution. Final-minute probabilities are transformed
but were excluded from fitting and remain prediction-only. The calibration changes
no live dashboard behavior. Do not tune against the untouched test period repeatedly.

## Time-aware calibration experiment

Use --method logistic_time when fitting. The constant method remains the default.
The correction is sigmoid(a + b(tau)*logit(p)), where
b(tau) = (1-tau/900)*b_late + (tau/900)*b_early.
Both endpoints are constrained positive, preserving probability ordering at each time.
The fixed ridge penalty also shrinks early/late differences. Final-minute samples
are excluded from fitting; this experiment evaluates minute-level trading only.
The observations argument accepts multiple paths. Their adjacent reports must have
identical EWMA settings. For previously calibrated observations the trainer explicitly
uses p_raw, avoiding double calibration. Duplicate window/checkpoints fail loudly.
Old constant logistic JSON artifacts remain supported.

Development: October 19-27 was already examined. Three expanding chronological splits
keep whole contracts together, using earlier windows for fitting and later windows for
validation. Results are in data/kalshi_research/time_calibration_development.json.
These are development diagnostics, not a clean held-out estimate.

Frozen comparison: fit both constant and time-aware corrections on October 19-27;
then test October 28 Eastern (2026-10-28T04:00:00Z to 2026-10-29T04:00:00Z)
without changing threshold, sizing, volatility, or fees. Each artifact creates its own
calibrated subfolder. Compare raw, constant and time-aware on identical observations.
After this result is examined, that day is no longer an untouched test period.
