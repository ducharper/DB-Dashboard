# LateDayPressureResearch — NinjaTrader 8

Research hypothesis: unusually heavy buying pressure immediately before the US equity close may persist for several minutes. This uses price and volume proxies. It does not observe forced traders, signed order flow, or Nasdaq auction imbalances, and is not a validated edge.

## Install

1. In NinjaTrader 8 open New → NinjaScript Editor. Under Strategies, create a strategy named `LateDayPressureResearch`.
2. Replace the entire generated source with the contents of `LateDayPressureResearch.cs`, then compile (F5). This is source code, not a NinjaScript import ZIP.
3. Set Tools → Options → General → Time zone to Eastern Time (US & Canada). Reload data/restart if prompted. The strategy reads platform timestamps directly; a different zone will test the wrong hours.
4. Open Strategy Analyzer and select this strategy, a single instrument, and Minute / 1. Choose a trading-hours template that includes the entire 09:30–16:00 Eastern window. ETH also works: overnight bars are excluded from the signal.
5. Include at least 21 complete sessions; the first 20 eligible sessions establish the volume baseline. Use a much longer sample for assessing performance. Enable commissions and enter plausible slippage for the instrument.

## Default rules

- Long only, quantity 1, at most one entry per day.
- At the bar ending 15:55 Eastern, compare the preceding five minutes' volume with the same window across the previous 20 eligible sessions.
- Require volume ≥1.5 times that mean, price above the session's approximate VWAP, and price above its 15:50 value.
- Submit a market entry after that bar closes. Submit a market exit at the close of the bar stamped 15:59. Historical market orders normally fill on the next bar; these are not guaranteed real-world execution prices.
- VWAP is approximated using typical bar price multiplied by volume; no paid Order Flow indicator is required.
- Skip sessions missing any minute between 09:31 and 15:55 (bar-end timestamps). Early closes cannot generate new entries. Session-close exit is a fallback. Gaps after entry can delay a timed exit. No protective price stop is included: this experiment tests the timed holding rule.

## Test the explanation

Run once with **Use pressure filter = true**, then again with it **false** on identical dates, instrument, commissions, slippage and quantity. False buys at the same time every eligible day after the same warm-up. Compare average net trade, drawdown, number of trades and results by year, not just total profit (the modes trade different numbers of days). Use unchanged rules on a later untouched period. A positive result is exploratory and does not establish that forced auction flow caused it.

For futures, this is a hypothesis about spillover around the US stock-market close, not the futures settlement time. Contract rolls can distort volume comparisons; examine rolls separately and do not assume a continuous contract is free of roll artifacts.

The source has not been compiled inside NinjaTrader in this workspace. Compile in the NinjaScript Editor before use. Start with Strategy Analyzer / simulation.
