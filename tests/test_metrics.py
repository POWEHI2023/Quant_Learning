import pandas as pd

from jquant.backtest.metrics import calculate_metrics
from jquant.config import MetricsConfig


def test_metrics_use_initial_equity() -> None:
    curve = pd.DataFrame(
        {"equity": [99.0, 110.0], "benchmark": [100.0, 105.0]},
        index=pd.bdate_range("2025-01-02", periods=2),
    )

    metrics = calculate_metrics(curve, MetricsConfig(), initial_equity=100.0)

    assert round(metrics["total_return"], 6) == 0.1
    assert round(metrics["benchmark_return"], 6) == 0.05
    assert round(metrics["max_drawdown"], 6) == -0.01
