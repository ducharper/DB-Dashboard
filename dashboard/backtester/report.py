import pandas as pd

from dashboard.backtester.metrics import total_return, annualized_volatility, sharpe_ratio, max_drawdown, annualized_return, \
    sortino_ratio, time_in_market, number_of_market_entries


def summarize_backtest(results: pd.DataFrame, periods_per_year: int, risk_free_rate: float) -> dict[str, float | int]:
    """ Uses the result dataframe to calculate performance metrics and package them in a readable format. """

    summary = {
        'Time in Market': time_in_market(results["Positions"]),
        'Number of Market Entries': number_of_market_entries(results["Positions"]),
        'Total Return': total_return(results["Strategy Returns"]),
        'Annualized Return': annualized_return(results["Strategy Returns"], periods_per_year),
        'Benchmark Return': total_return(results["Asset Returns"]),
        'Annualized Volatility': annualized_volatility(results["Strategy Returns"], periods_per_year),
        'Sharpe Ratio': sharpe_ratio(results["Strategy Returns"], periods_per_year, risk_free_rate),
        'Sortino Ratio': sortino_ratio(results["Strategy Returns"], periods_per_year, risk_free_rate),
        'Max Drawdown':  max_drawdown(results["Equity Curve"])
    }

    return summary

def format_summary(summary: dict[str, float]) -> str:
    """ Makes the summary more readable when printed. """

    return (
        "Backtest Summary:\n"
        "---------------------------\n"
        f"Time in Market:           {summary['Time in Market']:>8.2%}\n"
        f"Number of Market Entries: {summary['Number of Market Entries']:>8}\n"
        "---------------------------\n"
        f"Total Return:             {summary['Total Return']:>8.2%}\n"
        f"Benchmark Return:         {summary['Benchmark Return']:>8.2%}\n"
        "---------------------------\n"
        f"Annualized Volatility:    {summary['Annualized Volatility']:>8.2%}\n"
        f"Annualized Return:        {summary['Annualized Return']:>8.2%}\n"
        "---------------------------\n"
        f"Sharpe Ratio:             {summary['Sharpe Ratio']:>8.2f}\n"
        f"Sortino Ratio:            {summary['Sortino Ratio']:>8.2f}\n"
        f"Max Drawdown:             {summary['Max Drawdown']:>8.2%}\n"
    )
