from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from jquant.backtest.engine import BacktestEngine
from jquant.backtest.metrics import finite_metrics
from jquant.backtest.report import write_report
from jquant.config import load_config
from jquant.data.jqdata import JQDataSource
from jquant.strategy.small_cap_tech import SmallCapTechStrategy
from jquant.visualization import plot_backtest_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="聚宽本地量化回测工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="运行回测")
    run.add_argument("--config", default="config/tech_small_cap.toml")
    run.add_argument("--output", default="outputs/tech-small-cap")
    run.add_argument(
        "--prompt-credentials",
        action="store_true",
        help="交互式读取账号密码，不写入 shell 历史",
    )

    check = subparsers.add_parser("check-data", help="验证 JQData 登录并显示当日查询额度")
    check.add_argument(
        "--prompt-credentials",
        action="store_true",
        help="交互式读取账号密码，不写入 shell 历史",
    )
    filters = subparsers.add_parser("list-filters", help="显示策略已注册和当前启用的过滤器")
    filters.add_argument("--config", default="config/tech_small_cap.toml")
    plot = subparsers.add_parser("plot", help="将回测输出目录生成综合可视化报告")
    plot.add_argument("--input", required=True, help="包含回测 CSV/JSON 的输出目录")
    plot.add_argument("--output", help="PNG 输出路径，默认写入输入目录")
    plot.add_argument("--dpi", type=int, default=160)
    plot.add_argument("--show", action="store_true", help="保存后打开图形窗口")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "list-filters":
        config = load_config(args.config)
        strategy = SmallCapTechStrategy(config.strategy)
        for item in strategy.filter_status():
            marker = "[x]" if item["enabled"] else "[ ]"
            print(f"{marker} {item['name']}: {item['description']}")
        return
    if args.command == "plot":
        destination = plot_backtest_output(
            args.input, args.output, show=args.show, dpi=args.dpi
        )
        print(f"可视化报告已写入: {destination}")
        return
    if args.command == "check-data":
        source = _create_data_source(args.prompt_credentials)
        print(json.dumps(source.query_count(), ensure_ascii=False, indent=2))
        return

    config = load_config(args.config)
    source = _create_data_source(args.prompt_credentials)
    strategy = SmallCapTechStrategy(config.strategy)
    result = BacktestEngine(source, strategy, config).run()
    destination = write_report(result, Path(args.output))
    print(json.dumps(finite_metrics(result.metrics), ensure_ascii=False, indent=2))
    print(f"结果已写入: {destination.resolve()}")


def _create_data_source(prompt_credentials: bool) -> JQDataSource:
    if not prompt_credentials:
        return JQDataSource()
    username = getpass.getpass("JQData 账号: ")
    password = getpass.getpass("JQData 密码: ")
    return JQDataSource(username, password)
