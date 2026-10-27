from dashboard.api.schemas import MovingAverageConfig, MomentumConfig, MeanReversionConfig
from dashboard.strategies.base import Strategy
from dashboard.strategies.mean_reversion_strategy import MeanReversionStrategy
from dashboard.strategies.moving_average_strategy import MovingAverageStrategy
from dashboard.strategies.momentum_strategy import MomentumStrategy

def create_strategy(config: MovingAverageConfig | MomentumConfig | MeanReversionConfig) -> Strategy:
    """ Builds a strategy from validated API settings """

    if isinstance(config, MovingAverageConfig):
        return MovingAverageStrategy(
            short_window=config.short_window,
            long_window=config.long_window,
        )

    if isinstance(config, MomentumConfig):
        return MomentumStrategy(
            lookback=config.lookback,
        )

    if isinstance(config, MeanReversionConfig):
        return MeanReversionStrategy(
            mean_window=config.mean_window,
            entry_distance=config.entry_distance,
            exit_distance=config.exit_distance,
        )

    raise ValueError("Unsupported strategy configuration")