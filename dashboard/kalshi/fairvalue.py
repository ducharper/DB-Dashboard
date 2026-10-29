import numpy as np
import pandas as pd
from scipy.special import ndtr
from math import erf, sqrt, floor

W = 60 # prints in the settlement average

def settle_moments(S, tau, sigma, known_avg=None, discrete=True, window=W):
    """Mean and sd of the settlement average A_close given the state now.

    S, tau, sigma, known_avg may be scalars or equal-length arrays.
    In discrete mode tau counts one-second steps from the observed price
    to the LAST settlement print, not necessarily to the exchange close.
    Research decisions at t use the whole-second print at t-1, while the
    last settlement print is close-1, so tau=close-t is consistent.
    known_avg is required wherever tau < window (average of the prints seen so far
    inside the final window, including the current one).
    """

    ka_in = np.nan if known_avg is None else known_avg
    S, tau, sigma, ka = (np.asarray(x, dtype=float)
                         for x in np.broadcast_arrays(S, tau, sigma, ka_in))
    inside = tau < window

    if np.any(inside & ~np.isfinite(ka)):
        raise ValueError("known_avg is required (and must be finite) wherever tau < 60")
    ka = np.where(np.isfinite(ka), ka, 0.0)

    e = window - np.minimum(tau, window)
    mean = np.where(inside, (e * ka + tau * S) / window, S)

    if discrete:
        # sum of squared weights on the innovations; see derivation in README
        sq_inside = tau * (tau + 1) * (2 * tau + 1) / 6.0
        a = tau - (window - 1)
        sq_outside = window ** 2 * a + (window - 1) * window * (2 * window - 1) / 6.0
        var_sum = np.where(inside, sq_inside, sq_outside)
        sd = sigma * np.sqrt(np.maximum(var_sum, 0.0)) / window
    else:
        sd_in = (tau / window) * sigma * np.sqrt(np.maximum(tau, 0.0) / 3.0)
        sd_out = sigma * np.sqrt(np.maximum(tau - 2.0 * window / 3.0, 0.0))
        sd = np.where(inside, sd_in, sd_out)
    return mean, sd

def p_yes(S, K, tau, sigma, known_avg=None, discrete=True, window=W):
    """Model probability that the window settles Yes (A_close >= K)."""

    mean, sd = settle_moments(S, tau, sigma, known_avg, discrete, window)
    K = np.asarray(K, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (mean - K) / sd
    p = ndtr(z)
    # sd == 0 (e.g. tau == 0): outcome is deterministic
    return np.where(sd > 0, p, (mean >= K).astype(float))

def ewma_sigma(prices, step=5, halflife_s=600.0):
    """EWMA estimate of sigma ($ per sqrt-second) from a 1-second price array.

    The value at index t uses only prices[:t+1]. Early values are unreliable
    (warm-up); drop them when validating.
    """

    prices = np.asarray(prices, dtype=float)
    n = len(prices)
    idx = np.arange(0, n, step)
    d = np.diff(prices[idx])
    v = pd.Series(d ** 2 / step).ewm(halflife=halflife_s / step, adjust=False).mean().to_numpy()
    sig_idx = np.sqrt(np.concatenate([[np.nan], v]))
    out = np.full(n, np.nan)
    out[idx] = sig_idx
    return pd.Series(out).ffill().to_numpy()

def size_trade(*, probability, uncertainty, price, cost_allowance, bankroll, available_cash, existing_event_risk, kelly_fraction, trade_cap, event_cap):
    """Size a binary contract from validated inputs; never submits orders."""

    cost = price + cost_allowance
    if cost >= 1:
        raise ValueError('Price plus cost allowance must be less than the $1 payout.')
    conservative_p = max(0, probability - uncertainty)
    edge = conservative_p - cost
    fraction = max(0, edge / (1 - cost)) * kelly_fraction
    budget = max(0, min(bankroll * fraction, bankroll * trade_cap,
                       bankroll * event_cap - existing_event_risk, available_cash))
    contracts = floor(budget / cost)
    risk = contracts * cost
    return {'contracts': contracts, 'max_loss': risk, 'allocation': risk / bankroll,
            'expected_profit': contracts * (probability - cost),
            'conservative_profit': contracts * edge, 'loss_probability': 1 - probability,
            'conservative_probability': conservative_p, 'break_even': cost,
            'profit_if_win': contracts * (1 - cost),
            'decision': 'Research candidate' if contracts else 'Pass',
            'reason': 'Positive conservative edge within your limits.' if contracts else
                      'No conservative edge, insufficient budget, or event limit reached.'}
