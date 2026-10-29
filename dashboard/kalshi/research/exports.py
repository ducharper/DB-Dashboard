"""Reader-facing trade export; model diagnostics remain in detailed exports."""
from datetime import datetime, timezone

TRADE_FIELDS = [
    "ticker", "entry_time_utc", "minutes_remaining", "side", "contracts",
    "predicted_win_probability", "entry_price_usd", "fees_usd", "total_cost_usd",
    "expected_profit_usd", "result", "profit_usd", "cumulative_profit_usd",
]

def trade_view(trades):
    cumulative = 0.0
    result = []
    # Holding to settlement: accumulated profit is ordered by settlement time.
    for t in sorted(trades, key=lambda r: (r["close_time"], r["ticker"])):
        cumulative += float(t["pnl"])
        probability = float(t["p"]) if t["side"] == "yes" else 1-float(t["p"])
        won = int(t["outcome"]) if t["side"] == "yes" else 1-int(t["outcome"])
        result.append(dict(zip(TRADE_FIELDS, [
            t["ticker"], datetime.fromtimestamp(int(t["time"]), timezone.utc).isoformat(),
            float(t["tau"])/60, t["side"].upper(), int(t["quantity"]),
            probability, float(t["entry"]), float(t["fees"]),
            round(float(t["entry"])*int(t["quantity"])+float(t["fees"]), 10),
            float(t["edge"])*int(t["quantity"]), "WIN" if won else "LOSS",
            round(float(t["pnl"]), 10), round(cumulative, 10),
        ])))
    return result
