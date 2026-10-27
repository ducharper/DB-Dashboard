import pandas as pd

def build_trade_ledger(results: pd.DataFrame) -> pd.DataFrame:
    """ Displays each strategy trade into a more readable format """

    position_changes = results["Positions"].diff().fillna(0)

    trades = []
    entry_row = None
    for row_number, change in enumerate(position_changes):
        if change > 0:
            entry_row = row_number

        elif change < 0 and entry_row is not None:
            exit_row = row_number

            entry_date = results.index[entry_row - 1]
            exit_date = results.index[exit_row - 1]

            entry_price = results["Close"].iloc[entry_row - 1]
            exit_price = results["Close"].iloc[exit_row - 1]

            holding_period = exit_row - entry_row

            trade_returns = results["Strategy Returns"].iloc[entry_row:exit_row + 1]
            net_return = (1 + trade_returns).prod() - 1

            trades.append({
                "Entry Date": entry_date,
                "Exit Date": exit_date,
                "Entry Price": entry_price,
                "Exit Price": exit_price,
                "Holding Period": holding_period,
                "Net Return": net_return,
            })
            entry_row = None

    return pd.DataFrame(trades, columns=[
        "Entry Date",
        "Exit Date",
        "Entry Price",
        "Exit Price",
        "Holding Period",
        "Net Return",
    ])