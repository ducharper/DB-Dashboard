"""Run with python -m dashboard.kalshi.research.run --help."""
import argparse
import csv
import json
from pathlib import Path
from urllib.error import URLError
from .history import Client, download, epoch
from .observations import build, validation_frame
from .backtest import run
from .validate import brier, evaluate
from .exports import trade_view, TRADE_FIELDS

def score(rows):
    if not rows:
        return {"observations": 0}
    return {"observations": len(rows), "contracts": len({r["ticker"] for r in rows}),
            "brier": brier([r["p"] for r in rows], [r["outcome"] for r in rows])}

def save_csv(path, rows, fields=None):
    if not rows and fields is None:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def main():
    parser = argparse.ArgumentParser(description="Download and replay Bitcoin markets. No orders are placed.")
    parser.add_argument("--start", required=True, help="UTC ISO date, e.g. 2026-10-26T14:00:00Z")
    parser.add_argument("--end", required=True)
    parser.add_argument("--offline", action="store_true", help="Reuse downloaded dataset without network")
    parser.add_argument("--lookback", type=int, default=7200, help="Contiguous EWMA warm-up seconds")
    parser.add_argument("--halflife", type=float, default=600)
    parser.add_argument("--vol-step", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=.02)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--fee-rate", type=float, default=.07, help="Assumed historical taker coefficient; verify for selected period")
    parser.add_argument("--slippage", type=float, default=.01, help="Extra cost per contract for stress scenario")
    parser.add_argument("--calibration", help="Saved logistic correction; test dates must follow training")
    parser.add_argument("--output", default="data/kalshi_research")
    args = parser.parse_args()
    start,end = epoch(args.start),epoch(args.end)
    if end <= start or end-start > 31*86400:
        parser.error("Select a positive period of at most 31 days per download.")
    root = Path(args.output)
    folder = root / f"{start}_{end}"
    folder.mkdir(parents=True,exist_ok=True)
    target = folder/"dataset.json"
    try:
        if args.offline:
            dataset=json.loads(target.read_text())
        else:
            dataset=download(Client(root/"raw"),start,end,args.lookback)
            target.write_text(json.dumps(dataset),encoding="utf-8")
        rows, skipped, audit=build(dataset,args.lookback,halflife_s=args.halflife,step=args.vol_step)
        calibration_metadata = None
        if args.calibration:
            from .calibration import load, apply
            calibration_metadata = load(args.calibration)
            raw_rows = rows
            rows = apply(rows, calibration_metadata,
                         {k:vars(args)[k] for k in ("lookback","halflife","vol_step")})
            import hashlib
            calibration_id = hashlib.sha256(Path(args.calibration).read_bytes()).hexdigest()[:12]
            folder = folder / ("calibrated_"+calibration_id)
            folder.mkdir(parents=True,exist_ok=True)
            raw_trades, raw_summary = run(raw_rows,args.threshold,args.quantity,0,args.fee_rate)
            _, raw_stressed = run(raw_rows,args.threshold,args.quantity,args.slippage,args.fee_rate)
            save_csv(folder/"original_trades.csv",trade_view(raw_trades),TRADE_FIELDS)
            comparison = {"original":raw_summary,"original_stressed":raw_stressed,
                          "original_probabilities":score(raw_rows)}
        if rows:
            validation = evaluate(validation_frame(rows))
            validation.to_csv(folder/"validation.csv",index=False)
        trades,summary=run(rows,args.threshold,args.quantity,0,args.fee_rate)
        stressed,stress_summary=run(rows,args.threshold,args.quantity,args.slippage,args.fee_rate)
        cut=start+(end-start)*.7
        partitions={name:[r for r in rows if (r["close_time"]<=cut)==early]
                    for name,early in (("earlier",True),("later",False))}
        report={"config":vars(args), "markets_downloaded":len(dataset["markets"]),
                "baseline":summary,"stressed":stress_summary,"probabilities":score(rows),
                "by_time_remaining":{str(t):score([r for r in rows if r["tau"]==t]) for t in sorted({r["tau"] for r in rows})},
                "periods":{name:{"probabilities":score(group),
                                "backtest":run(group,args.threshold,args.quantity,0,args.fee_rate)[1]}
                           for name,group in partitions.items()},
                "limitations":["Minute candle closes are assumed fill prices; no depth or latency simulation.",
                               "Standard fee coefficient is an assumption; verify historical series fees.",
                               "Final sub-minute trading excluded. Settlement sampling audit is diagnostic.",
                               "The later period is a holdout only if parameters were chosen without inspecting it.",
                               "No statistical reliability verdict; a small sample cannot establish an edge."]}
        if calibration_metadata is not None:
            report["calibration"] = calibration_metadata
            report["comparison"] = {**comparison,"calibrated":summary,
                                    "calibrated_stressed":stress_summary}
            report["limitations"].append("mean, sd and z describe the raw distribution; calibration adjusts probabilities only.")
        for name,items in (("observations",rows),("trades_detailed",trades),("stressed_trades_detailed",stressed),
                           ("skipped",skipped),("settlement_audit",audit)):
            save_csv(folder/(name+".csv"),items)
        save_csv(folder/"trades.csv",trade_view(trades),TRADE_FIELDS)
        save_csv(folder/"stressed_trades.csv",trade_view(stressed),TRADE_FIELDS)
        (folder/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        display = ({"comparison":report["comparison"]} if calibration_metadata is not None
                   else {"baseline":summary,"stressed":stress_summary})
        print(json.dumps({**display,"observations":len(rows),"skipped":len(skipped)},indent=2))
        print("Results:",folder.resolve())
        if not rows:
            print("No usable observations. Inspect skipped.csv; this is not evidence of no edge.")
    except (ValueError, OSError, KeyError, TypeError, URLError) as exc:
        print("Research stopped:",str(exc))
        print("Cached downloads are retained. Fix the issue and rerun.")
        raise SystemExit(1)

if __name__=="__main__":
    main()
