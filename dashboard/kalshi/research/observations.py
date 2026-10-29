"""Causal observations; decisions at t use whole-second prints through t-1."""
import math
import statistics
import numpy as np
import pandas as pd
from dashboard.kalshi.fairvalue import ewma_sigma, p_yes, settle_moments
from .history import epoch

def seconds(ticks):
    """Legacy helper: last tick strictly before each boundary."""
    by_time = checked_ticks(ticks)
    result = {}
    for t, value in sorted(by_time.items()):
        result[t//1000+1] = value
    return result

def checked_ticks(ticks):
    result = {}
    for row in ticks:
        t, value = int(row["time"]), float(row["value"])
        if not math.isfinite(value) or value <= 0 or not 10**12 < t < 10**14:
            raise ValueError("Invalid BRTI price or millisecond timestamp")
        if t in result and result[t] != value:
            raise ValueError("Conflicting BRTI observations")
        result[t] = value
    return result

def volatility(prices, warmup_s, step, halflife_s):
    """Reset EWMA and warm-up after a missing whole-second observation."""
    result = {}
    times = sorted(prices)
    cuts = [0]+[i for i in range(1,len(times)) if times[i] != times[i-1]+1]+[len(times)]
    for a,b in zip(cuts,cuts[1:]):
        segment = times[a:b]
        if len(segment) <= warmup_s:
            continue
        estimates = ewma_sigma([prices[t] for t in segment], step=step, halflife_s=halflife_s)
        for i in range(warmup_s,len(segment)):
            result[segment[i]] = float(estimates[i])
    return result

def build(dataset, lookback=7200, *, halflife_s=600, step=5,
          final_checkpoints=(30,10), cluster="day"):
    """lookback is EWMA warm-up seconds, retained for caller compatibility.
    At decision t: S is BRTI(t-1), settlement prints are close-60 ... close-1.
    Consequently model tau=close-t is the number of future one-second steps
    from the latest admitted print to the final settlement print.
    Outcome and z are evaluation labels only, never inputs to prediction.
    """
    if not isinstance(lookback,int) or lookback < 30:
        raise ValueError("EWMA warm-up must be at least 30 seconds")
    if not isinstance(step,int) or step < 1 or not math.isfinite(halflife_s) or halflife_s <= 0:
        raise ValueError("Invalid EWMA settings")
    if cluster not in ("window","hour","day"):
        raise ValueError("cluster must be window, hour or day")
    if any(not isinstance(t,int) or not 0 < t < 60 for t in final_checkpoints):
        raise ValueError("Final checkpoints must be integer seconds from 1 to 59")
    ticks = checked_ticks(dataset["ticks"])
    # Only exact whole-second prints. No invented prices or forward-filled gaps.
    prices = {t//1000+1:v for t,v in ticks.items() if t%1000 == 0}
    sigmas = volatility(prices,lookback,step,halflife_s)
    rows, skipped, audit = [], [], []
    for market in dataset["markets"]:
        ticker = market["ticker"]
        closing = epoch(market["close_time"])
        opening = epoch(market["open_time"]) if market.get("open_time") else closing-900
        try:
            strike = float(market["floor_strike"])
            if not math.isfinite(strike) or strike <= 0 or closing-opening != 900:
                raise ValueError()
            if market.get("strike_type") not in ("greater","greater_or_equal"):
                raise ValueError()
            if market.get("is_provisional") or market.get("result") not in ("yes","no"):
                raise ValueError()
        except (KeyError,TypeError,ValueError):
            skipped.append({"ticker":ticker,"reason":"Missing/unsupported strike, duration or final outcome"})
            continue
        try:
            actual = float(market["expiration_value"])
            if not math.isfinite(actual):
                actual = None
        except (KeyError,ValueError,TypeError):
            actual = None
        item = {"ticker":ticker,"strike":strike,"published_expiration":actual}
        for label,boundary in (("opening_average",opening),("closing_average",closing)):
            samples = [prices.get(s) for s in range(boundary-59,boundary+1)]
            item[label] = statistics.mean(samples) if all(v is not None for v in samples) else None
        item["opening_error"] = item["opening_average"]-strike if item["opening_average"] is not None else None
        item["closing_error"] = item["closing_average"]-actual if item["closing_average"] is not None and actual is not None else None
        audit.append(item)
        candles = {}
        for candle in dataset["candles"].get(ticker,[]):
            t = int(candle["end_period_ts"])
            if t in candles:
                raise ValueError("Duplicate candle timestamp for "+ticker)
            candles[t] = candle
        decisions = set(range(opening+60,closing,60)) | {closing-tau for tau in final_checkpoints}
        for t in sorted(decisions):
            try:
                sigma = sigmas.get(t)
                if t not in prices or sigma is None or not math.isfinite(sigma) or sigma <= 0:
                    raise ValueError("Missing BRTI, incomplete EWMA warm-up, or zero volatility")
                tau = closing-t
                known = None
                if tau < 60:
                    samples = [prices.get(s) for s in range(closing-59,t+1)]
                    if any(v is None for v in samples):
                        raise ValueError("Missing recorded settlement print")
                    known = statistics.mean(samples)
                mean,sd = settle_moments(prices[t],tau,sigma,known,discrete=True)
                mean,sd = float(mean),float(sd)
                probability = float(p_yes(prices[t],strike,tau,sigma,known,discrete=True))
                bid = ask = None
                quote_reason = "No matching minute quote; prediction only"
                candle = candles.get(t) if tau >= 60 else None
                if candle:
                    try:
                        def quote(side):
                            values = candle[side]
                            if "close_dollars" in values:
                                return float(values["close_dollars"])
                            v = float(values["close"])
                            return v if market["_tier"] == "historical" else v/100
                        bid,ask = quote("yes_bid"),quote("yes_ask")
                        if not 0 < bid <= ask < 1:
                            raise ValueError()
                        quote_reason = ""
                    except (KeyError,TypeError,ValueError):
                        bid = ask = None
                        quote_reason = "Invalid quote; prediction only"
                group = ticker if cluster=="window" else str(pd.Timestamp(closing,unit="s",tz="UTC").floor("h" if cluster=="hour" else "D"))
                rows.append({"ticker":ticker,"window_id":ticker,"group":group,"time":t,
                             "ts":pd.Timestamp(t,unit="s",tz="UTC").isoformat(),
                             "source_time":t-1,"close_time":closing,"tau":tau,
                             "spot":prices[t],"strike":strike,"sigma":sigma,
                             "known_avg":known,"mean":mean,"sd":sd,"p":probability,"p_model":probability,
                             "bid":bid,"ask":ask,"p_market":(bid+ask)/2 if bid is not None else None,
                             "trade_eligible":bid is not None,"quote_reason":quote_reason,
                             "outcome":int(market["result"]=="yes"),"settle":actual,
                             "z":(actual-mean)/sd if actual is not None and sd>0 else None})
            except (KeyError,TypeError,ValueError) as exc:
                skipped.append({"ticker":ticker,"time":t,"reason":str(exc)})
    return rows,skipped,audit

def validation_frame(rows):
    return pd.DataFrame(rows)
