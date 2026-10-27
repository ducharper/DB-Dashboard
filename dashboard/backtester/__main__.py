from dashboard.backtester.plotting import plot_backtest
from dashboard.backtester.report import format_summary
from dashboard.backtester.runner import run_backtest
from dashboard.strategies.moving_average_strategy import MovingAverageStrategy

def main() -> None:
    result, summary, ledger = run_backtest(
        symbol="AAPL",
        start="2020-01-01",
        end="2026-01-01",
        strategy=MovingAverageStrategy(20, 50),
        initial_cash=10_000,
        cost_bps=5,
        periods_per_year=252,
        risk_free_rate=0.04,
    )

    print(format_summary(summary))
    print(ledger.to_string(index=False))
    plot_backtest(result)

if __name__ == "__main__":
    main()