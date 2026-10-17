import math


def stock_exposure(quantity: float, price: float) -> float:
    """Return signed stock or ETF exposure in the instrument's currency."""
    if not math.isfinite(quantity):
        raise ValueError("Quantity must be finite.")
    if not math.isfinite(price):
        raise ValueError("Price must be finite.")
    if price < 0:
        raise ValueError("Price must be positive.")

    return quantity * price

def exposure_ratio(exposure: float, account_equity: float) -> float:
    """Return signed exposure as a fraction of account equity."""
    if not math.isfinite(account_equity):
        raise ValueError("Account equity must be finite.")
    if not math.isfinite(exposure):
        raise ValueError("Exposure must be finite.")
    if account_equity <= 0:
        raise ValueError("Account equity must be positive.")

    return exposure / account_equity

def stock_scenario_pnl(
        quantity: float,
        price: float,
        price_change: float,
) -> float:
    """Return hypothetical P&L from a proportional price move."""
    if not math.isfinite(quantity):
        raise ValueError("Quantity must be finite.")
    if price < 0:
        raise ValueError("Price must be positive.")
    if not math.isfinite(price_change):
        raise ValueError("Price change must be finite.")
    if price_change < -1:
        raise ValueError("Price change must be greater than or equal to -1; price cannot decrease by more than 100%.")

    return stock_exposure(quantity, price) * price_change

def summarize_stock_position(
        quantity: float,
        price: float,
        account_equity: float,
        price_change: float,
) -> dict[str, float]:
    """Return summary statistics for a position."""
    if not math.isfinite(quantity):
        raise ValueError("Quantity must be finite.")
    if price < 0:
        raise ValueError("Price must be positive.")
    if not math.isfinite(price_change):
        raise ValueError("Price change must be finite.")
    if not math.isfinite(account_equity):
        raise ValueError("Account equity must be finite.")
    if price_change < -1:
        raise ValueError("Price change must be greater than or equal to -1; price cannot decrease by more than 100%.")

    exposure = stock_exposure(quantity, price)
    ratio = exposure_ratio(exposure, account_equity)
    pnl = stock_scenario_pnl(quantity, price, price_change)
    account_return = exposure_ratio(pnl, account_equity)

    summary = {
        "exposure": exposure,
        "exposure_ratio": ratio,
        "scenario_pnl": pnl,
        "scenario_account_return": account_return,
    }

    return summary