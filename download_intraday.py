"""Download one completed session of minute bars to a new local research folder."""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from backtester.errors import MarketDataUnavailableError
from backtester.intraday_data import download_minutes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', default='AAPL')
    parser.add_argument('--date', required=True, type=date.fromisoformat, help='Completed session, YYYY-MM-DD')
    parser.add_argument('--exchange', default='', help='Primary exchange, e.g. NASDAQ')
    args = parser.parse_args()
    print(f'Requesting {args.symbol} on {args.date}: 1-minute regular-session TRADES.', flush=True)
    try:
        frame = download_minutes(args.symbol, args.date, args.exchange)
    except MarketDataUnavailableError as exc:
        parser.exit(1, f'Download failed: {exc}\n')
    # A new directory preserves earlier downloads and keeps user input out of paths.
    output = Path(__file__).resolve().parent / 'data' / 'intraday' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    exported = frame.copy()
    exported.insert(0, 'timestamp_new_york', frame.index.tz_convert('America/New_York'))
    exported.to_csv(output / 'bars.csv')
    (output / 'metadata.json').write_text(json.dumps(frame.attrs['data_info'], indent=2), encoding='utf-8')
    print(f'Saved {len(frame)} bars to {output / "bars.csv"}')
    print(f'Coverage (New York): {exported.iloc[0, 0]} through {exported.iloc[-1, 0]}')
    for warning in frame.attrs['data_info']['warnings']:
        print(f'Note: {warning}')


if __name__ == '__main__':
    main()
