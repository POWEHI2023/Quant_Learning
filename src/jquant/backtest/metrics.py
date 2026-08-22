from __future__ import annotations

import math

import numpy as np
import pandas as pd

from jquant.config import MetricsConfig


def calculate_metrics(
    equity_curve: pd.DataFrame,
    config: MetricsConfig,
    initial_equity: float | None = None,
) -> dict[str, float]:
    if equity_curve.empty:
        return {}
    equity = equity_curve["equity"].astype(float)
    returns = equity.pct_change()
    if initial_equity is not None:
        returns.iloc[0] = equity.iloc[0] / initial_equity - 1
    returns = returns.dropna()
    years = len(returns) / config.annual_trading_days
    starting_value = initial_equity if initial_equity is not None else equity.iloc[0]
    total_return = equity.iloc[-1] / starting_value - 1
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0
    annual_volatility = (
        returns.std(ddof=1) * math.sqrt(config.annual_trading_days)
        if len(returns) > 1
        else 0.0
    )
    sharpe = (
        (annual_return - config.risk_free_rate) / annual_volatility
        if annual_volatility > 0
        else float("nan")
    )
    peaks = equity.cummax()
    if initial_equity is not None:
        peaks = peaks.clip(lower=initial_equity)
    drawdown = equity / peaks - 1
    max_drawdown = float(drawdown.min())

    metrics = {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "annual_volatility": float(annual_volatility),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": max_drawdown,
        "final_equity": float(equity.iloc[-1]),
    }
    if "benchmark" in equity_curve and equity_curve["benchmark"].notna().sum() >= 2:
        benchmark = equity_curve["benchmark"].dropna().astype(float)
        benchmark_return = benchmark.iloc[-1] / benchmark.iloc[0] - 1
        metrics["benchmark_return"] = float(benchmark_return)
        metrics["excess_return"] = float(total_return - benchmark_return)
    return metrics


def finite_metrics(metrics: dict[str, float]) -> dict[str, float | None]:
    return {key: value if np.isfinite(value) else None for key, value in metrics.items()}
