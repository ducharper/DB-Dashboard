import pandas as pd

def calculate_turnover(
        positions: pd.Series
) -> pd.Series:
    """ Calculates position turnover. """

    return positions.diff().abs().fillna(0)

def calculate_transaction_costs(
        positions: pd.Series,
        cost_bps: float
) -> pd.Series:
    """ Calculates the transaction costs resulting from turnover. """

    turnover = calculate_turnover(positions)
    rate = cost_bps / 10000

    return turnover * rate