"""First qualifying entry per contract; candle fills are hypothetical."""
from decimal import Decimal, ROUND_CEILING
import math

def fee(price, quantity=1, rate=.07):
    p = Decimal(str(price))
    return float((Decimal(str(rate))*quantity*p*(1-p)*100).to_integral_value(rounding=ROUND_CEILING)/100)

def run(rows, threshold=.02, quantity=1, slippage=0., fee_rate=.07):
    if quantity < 1 or int(quantity) != quantity:
        raise ValueError("Quantity must be a positive integer")
    if not all(math.isfinite(v) and v >= 0 for v in (threshold, slippage, fee_rate)):
        raise ValueError("Invalid costs or threshold")
    trades, entered = [], set()
    for row in sorted(rows, key=lambda r: (r["time"], r["ticker"])):
        if row["ticker"] in entered:
            continue
        if not row.get("trade_eligible", True):
            continue
        p = row["p"]
        if not 0 <= p <= 1 or not 0 < row["bid"] <= row["ask"] < 1 or row["outcome"] not in (0,1):
            raise ValueError("Invalid observation")
        choices = []
        for side, probability, quote in (("yes",p,row["ask"]), ("no",1-p,round(1-row["bid"],10))):
            cost = round(quote+slippage,10)
            if not 0 < cost < 1:
                continue
            fees = fee(cost, quantity, fee_rate)
            edge = probability-cost-fees/quantity
            choices.append((edge, side, cost, fees))
        if not choices:
            continue
        edge, side, cost, fees = max(choices)
        if edge <= threshold:
            continue
        win = row["outcome"] if side == "yes" else 1-row["outcome"]
        trades.append({**row, "side": side, "quantity": quantity, "entry": cost, "fees": fees,
                       "edge": edge, "pnl": quantity*(win-cost)-fees})
        entered.add(row["ticker"])
    equity = peak = drawdown = 0.
    for trade in sorted(trades, key=lambda r:r["close_time"]):
        equity += trade["pnl"]
        peak = max(peak,equity)
        drawdown = max(drawdown,peak-equity)
    return trades, {"trades":len(trades), "net_profit":equity, "max_drawdown":drawdown,
                    "win_rate":sum(t["pnl"]>0 for t in trades)/len(trades) if trades else None}
