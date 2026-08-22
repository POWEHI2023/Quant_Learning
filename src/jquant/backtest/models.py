from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class Position:
    code: str
    shares: int
    average_cost: float


@dataclass(frozen=True)
class Order:
    date: date
    code: str
    side: str
    shares: int
    price: float
    notional: float
    fees: float
    status: str = "filled"
    reason: str = ""


@dataclass(frozen=True)
class RebalancePlan:
    signal_date: date
    execution_date: date
    targets: tuple[str, ...]


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    orders: list[Order] = field(default_factory=list)
    plans: list[RebalancePlan] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

