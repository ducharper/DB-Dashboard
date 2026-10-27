import pandas as pd

from dashboard.strategies.base import Strategy

class MovingAverageStrategy(Strategy):
    def __init__(self, short_window: int, long_window: int):
        """ Initializes the moving average strategy with given values for the short and long windows for rolling average. """

        if short_window >= long_window or short_window <= 0 or long_window <= 0:
            raise ValueError("Invalid window sizes")

        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """ Generates signals based on moving averages. """

        short_series = data["Close"].rolling(self.short_window).mean()
        long_series = data["Close"].rolling(self.long_window).mean()

        signal_series = (short_series > long_series).astype(int)
        return signal_series


