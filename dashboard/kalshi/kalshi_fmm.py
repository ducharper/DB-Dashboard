"""Experimental settlement probability and hypothetical trade sizing.

p_yes is an uncalibrated continuous-price approximation supplied for research.
The dashboard sizing endpoint uses user-supplied probabilities, not p_yes.
"""
from math import erf, sqrt, floor

def norm_cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))

def p_yes(S, K, tau, sigma, known_avg=None):
    """S: index now, K: opening reference, tau: seconds to close,
    sigma: $ per sqrt(second), known_avg: mean of index prints so far
    inside the final 60s window (needed only when tau < 60)."""

    if tau >= 60:
        mean, sd = S, sigma * sqrt(tau - 40)
    else:
        e = 60 - tau
        mean = (e * known_avg + tau * S) / 60
        sd = (tau / 60) * sigma * sqrt(tau / 3)
    if sd == 0:
        return float(mean >= K)
    return norm_cdf((mean - K) / sd)

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
