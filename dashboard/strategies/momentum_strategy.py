import pandas as pd
from dashboard.strategies.base import Strategy

class MomentumStrategy(Strategy):
    def __init__(self, lookback: int):
        """ Initializes the momentum strategy with a lookback variable to compare current and previous close. """

        if lookback <= 0:
            raise ValueError('Lookback must be greater than 0')

        self.lookback = lookback

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """ Generates the signals based on momentum. """

        previous_close = data["Close"].shift(self.lookback)
        signals = (data["Close"] > previous_close).astype(int)

        return signals