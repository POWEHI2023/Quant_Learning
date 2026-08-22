from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from jquant.backtest.metrics import finite_metrics
from jquant.backtest.models import BacktestResult


def write_report(result: BacktestResult, output_dir: str | Path) -> Path:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    result.equity_curve.to_csv(destination / "equity_curve.csv", index_label="date")
    pd.DataFrame([asdict(order) for order in result.orders]).to_csv(
        destination / "orders.csv", index=False
    )
    plans = [
        {
            "signal_date": plan.signal_date,
            "execution_date": plan.execution_date,
            "targets": ",".join(plan.targets),
        }
        for plan in result.plans
    ]
    pd.DataFrame(plans).to_csv(destination / "rebalance_plans.csv", index=False)
    with (destination / "metrics.json").open("w", encoding="utf-8") as stream:
        json.dump(finite_metrics(result.metrics), stream, ensure_ascii=False, indent=2)
    return destination

