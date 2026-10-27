from datetime import date, datetime
from typing import Self, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

class MovingAverageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["moving_average"]
    short_window: int = Field(default=20, gt=0, strict=True)
    long_window: int = Field(default=50, gt=0, strict=True)

    @model_validator(mode="after")
    def validate_windows(self) -> Self:
        if self.short_window >= self.long_window:
            raise ValueError("Short window must be less than long window")

        return self

class MomentumConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["momentum"]
    lookback: int = Field(default=20, gt=0, strict=True)

class MeanReversionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["mean_reversion"]
    mean_window: int = Field(default=20, gt=0, strict=True)
    entry_distance: float = Field(default=0.05, gt=0, lt=1, strict=True)
    exit_distance: float = Field(default=0.01, ge=0, lt=1, strict=True)

    @model_validator(mode="after")
    def validate_distances(self) -> Self:
        if self.exit_distance >= self.entry_distance:
            raise ValueError("Exit distance must be less than than entry distance")

        return self

class BacktestRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    symbol: str = Field(min_length=1)
    data_source: Literal['yahoo', 'ibkr'] = 'yahoo'
    bar_size: Literal['1 day', '1 min'] = '1 day'
    ibkr_primary_exchange: str = Field(default='', max_length=30, pattern=r'^[A-Za-z0-9.]*$')
    start: date
    end: date

    initial_cash: float = Field(default=10_000, gt=0)
    cost_bps: float = Field(default=5, ge=0)
    periods_per_year: int = Field(default=252, gt=0)
    risk_free_rate: float = Field(default=0.04, gt=-1)

    strategy: MovingAverageConfig | MomentumConfig | MeanReversionConfig = Field(
        discriminator="name"
    )

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.start >= self.end:
            raise ValueError("Start date must be before end")
        if self.bar_size == '1 min':
            if self.data_source != 'ibkr':
                raise ValueError('One-minute bars require IBKR.')
            if (self.end - self.start).days > 31:
                raise ValueError('Minute downloads are limited to 31 calendar days per run.')
            if self.cost_bps >= 10000:
                raise ValueError('Trading cost must be below 10000 bps.')
            self.periods_per_year = 252  # Intraday returns are aggregated by session.

        return self

class EquityPoint(BaseModel):
    date: date | datetime
    strategy: float
    benchmark: float

class TradeResponse(BaseModel):
    entry_date: date | datetime
    exit_date: date | datetime
    entry_price: float
    exit_price: float
    holding_period: int
    net_return: float

class DataInfo(BaseModel):
    source: Literal['yahoo', 'ibkr']
    price_basis: str
    first_date: date
    last_date: date
    bar_count: int
    fetched_at: str
    warnings: list[str]


class BacktestResponse(BaseModel):
    engine: Literal['python'] = 'python'
    data_info: DataInfo | None = None
    run_id: str | None = None
    completed_at: str | None = None
    summary: dict[str, float | None]
    equity: list[EquityPoint]
    trades: list[TradeResponse]
