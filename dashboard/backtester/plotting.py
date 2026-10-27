import pandas as pd
import matplotlib.pyplot as plt

def plot_backtest(result: pd.DataFrame) -> None:
    """ Plots the strategy and benchmark curves onto a graph to allow for easier comparison over time. """

    initial_cash = result["Equity Curve"].iloc[0]
    benchmark_curve = initial_cash * (1 + result["Asset Returns"]).cumprod()

    result["Equity Curve"].plot(label = "Strategy")
    benchmark_curve.plot(label = "Benchmark")

    plt.title("Strategy vs. Benchmark")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    
    plt.legend()
    plt.grid(alpha = 0.3)
    plt.tight_layout()
    plt.show()