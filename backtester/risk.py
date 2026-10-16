import math


def stock_exposure(quantity: float, price: float) -> float:
    """Return signed stock or ETF exposure in the instrument's currency."""
    if not math.isfinite(quantity):
        raise ValueError("Quantity must be finite.")

    return quantity * price

def exposure_ratio(exposure: float, account_equity: float) -> float:
    """Return signed exposure as a fraction of account equity."""

    return exposure / account_equity

