import pandas as pd

from dashboard.backtester.friction import calculate_transaction_costs
from dashboard.strategies.base import Strategy

class BackTestEngine:
    def __init__(self, data: pd.DataFrame, strategy: Strategy, initial_cash: float, cost_bps: float):
        """ Initializes the backtest engine with the given data, strategy, principle, and transaction cost. """

        if data.empty:
            raise ValueError("The DataFrame cannot be empty")

        if initial_cash <= 0:
            raise ValueError("The initial cash must be positive and nonzero")

        if cost_bps < 0:
            raise ValueError("The transaction cost cannot be negative")

        if "Close" not in data.columns:
            raise KeyError("The DataFrame must contain a 'Close' column")

        self.data = data.copy()
        self.strategy = strategy
        self.initial_cash = initial_cash
        self.cost_bps = cost_bps

    def run(self) -> pd.DataFrame:
        """ Runs a backtest with DataFrame and a chosen strategy. """

        signals = self.strategy.generate_signals(self.data)
        positions = signals.shift(1).fillna(0)
        asset_returns = self.data["Close"].pct_change().fillna(0)

        gross_strategy_returns = positions * asset_returns
        strategy_returns = gross_strategy_returns - calculate_transaction_costs(positions, self.cost_bps)
        equity_curve = self.initial_cash * (1 + strategy_returns).cumprod()

        results = pd.DataFrame({
            "Close": self.data["Close"],
            "Signals": signals,
            "Positions": positions,
            "Asset Returns": asset_returns,
            "Strategy Returns": strategy_returns,
            "Equity Curve": equity_curve
        })

        return results
