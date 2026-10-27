import pandas as pd
from abc import ABC, abstractmethod

class Strategy(ABC):

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """ Generates desired positions from market data. """

        pass
